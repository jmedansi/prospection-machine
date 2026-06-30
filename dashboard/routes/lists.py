# -*- coding: utf-8 -*-
"""
dashboard/routes/lists.py — Routes API listes de leads

Gestion des listes manuelles de leads (ex: "À auditer aujourd'hui").
Couche HTTP mince : valide les paramètres, délègue à la DB, retourne JSON.
Aucune logique métier — les actions groupées appellent les agents/endpoints existants.
"""
import csv
import io
from datetime import datetime
from flask import Blueprint, jsonify, request, Response
from database.connection import get_conn, logger

lists_bp = Blueprint("lists", __name__)

CONTACTED_STATUSES = {
    "archive", "desabonne", "contacte", "envoye", "email_sent", "repondu"
}
CONTACTED_PROSPECTION_STATUSES = CONTACTED_STATUSES.union({
    "step1_envoye", "lien_envoye", "linkedin_envoye", "formulaire_envoye", "whatsapp_envoye"
})

_DEFAULT_LIST_NAME = "Leads sans liste"
_DEFAULT_LIST_DESCRIPTION = "Leads scrapés qui ne sont encore assignés à aucune liste. Rafraîchis cette liste pour retrouver les nouveaux leads."
_DEFAULT_LIST_ICON = "📌"

_SECTOR_LABELS = {
    "immobilier": "Immobilier",
    "courtage": "Courtage",
    "concessionnaires_auto": "Concessionnaires Auto",
    "cliniques_esthetiques": "Cliniques Esthétiques",
    "ecoles_formation": "Écoles / Formation",
}

_SECTOR_ICONS = {
    "immobilier": "🏡",
    "courtage": "🏢",
    "concessionnaires_auto": "🚗",
    "cliniques_esthetiques": "💆",
    "ecoles_formation": "🎓",
}


def _human_sector_name(secteur: str) -> str:
    if not secteur:
        return "Secteur"
    return _SECTOR_LABELS.get(secteur, secteur.replace("_", " ").title())


def _chunked(iterable: list, size: int) -> list[list]:
    return [iterable[i:i + size] for i in range(0, len(iterable), size)]


def _get_uncontacted_lead_ids(conn, secteur: str) -> list[int]:
    statut_placeholders = ", ".join("?" for _ in CONTACTED_STATUSES)
    pros_statut_placeholders = ", ".join("?" for _ in CONTACTED_PROSPECTION_STATUSES)
    query = f"""
        SELECT lb.id
        FROM leads_bruts lb
        LEFT JOIN leads_audites la ON la.lead_id = lb.id
        WHERE LOWER(lb.secteur) = LOWER(?)
          AND COALESCE(LOWER(lb.statut), '') NOT IN ({statut_placeholders})
          AND COALESCE(LOWER(la.statut_prospection), '') NOT IN ({pros_statut_placeholders})
        ORDER BY lb.rating DESC, lb.nb_avis DESC, lb.date_scraping DESC
    """
    params = [secteur] + list(CONTACTED_STATUSES) + list(CONTACTED_PROSPECTION_STATUSES)
    rows = conn.execute(query, params).fetchall()
    return [r[0] for r in rows]


def _create_list_with_leads(conn, name: str, description: str, lead_ids: list[int], icon: str = "📋") -> int:
    cur = conn.execute(
        "INSERT INTO lead_lists (nom, description, icone) VALUES (?, ?, ?)",
        (name, description, icon)
    )
    list_id = cur.lastrowid
    for lead_id in lead_ids:
        try:
            conn.execute(
                "INSERT INTO lead_list_items (list_id, lead_id) VALUES (?, ?)",
                (list_id, lead_id)
            )
        except Exception:
            pass
    conn.commit()
    return list_id


def _get_unlisted_lead_ids(conn) -> list[int]:
    rows = conn.execute("""
        SELECT lb.id
        FROM leads_bruts lb
        LEFT JOIN lead_list_items lli ON lli.lead_id = lb.id
        WHERE lli.id IS NULL
        ORDER BY lb.date_scraping DESC, lb.rating DESC, lb.nb_avis DESC
    """).fetchall()
    return [r[0] for r in rows]


def _get_or_create_default_list(conn) -> int:
    row = conn.execute(
        "SELECT id FROM lead_lists WHERE nom = ?",
        (_DEFAULT_LIST_NAME,)
    ).fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO lead_lists (nom, description, icone) VALUES (?, ?, ?)",
        (_DEFAULT_LIST_NAME, _DEFAULT_LIST_DESCRIPTION, _DEFAULT_LIST_ICON)
    )
    conn.commit()
    return cur.lastrowid


def _refresh_default_list(conn) -> dict:
    default_list_id = _get_or_create_default_list(conn)
    conn.execute(
        "DELETE FROM lead_list_items WHERE list_id = ?",
        (default_list_id,)
    )
    lead_ids = _get_unlisted_lead_ids(conn)
    for lead_id in lead_ids:
        try:
            conn.execute(
                "INSERT INTO lead_list_items (list_id, lead_id) VALUES (?, ?)",
                (default_list_id, lead_id)
            )
        except Exception:
            pass
    conn.commit()
    return {"list_id": default_list_id, "count": len(lead_ids)}


@lists_bp.route("/api/lists/reset", methods=["POST"])
def api_lists_reset():
    """Supprime toutes les listes existantes et recrée la liste par défaut pour les leads non assignés."""
    try:
        with get_conn() as conn:
            conn.execute("DELETE FROM lead_lists")
            conn.commit()
            result = _refresh_default_list(conn)
        return jsonify({"success": True, "default_list": result}), 200
    except Exception as e:
        logger.error(f"api_lists_reset → {e}")
        return jsonify({"error": str(e)}), 500


@lists_bp.route("/api/lists/default/refresh", methods=["POST"])
def api_lists_default_refresh():
    """Rafraîchit la liste par défaut avec les leads qui n'appartiennent à aucune liste."""
    try:
        with get_conn() as conn:
            result = _refresh_default_list(conn)
        return jsonify({"success": True, "default_list": result}), 200
    except Exception as e:
        logger.error(f"api_lists_default_refresh → {e}")
        return jsonify({"error": str(e)}), 500


@lists_bp.route("/api/lists/sector-batches", methods=["POST"])
def api_lists_create_sector_batches():
    """Crée automatiquement des listes de 50 leads par secteur en excluant les leads déjà contactés."""
    try:
        data = request.get_json() or {}
        sectors = data.get("sectors")
        batch_size = int(data.get("batch_size", 50))
        if batch_size < 1 or batch_size > 1000:
            return jsonify({"error": "batch_size doit être entre 1 et 1000"}), 400

        if sectors is None:
            with get_conn() as conn:
                sectors = [r[0] for r in conn.execute(
                    "SELECT DISTINCT secteur FROM leads_bruts WHERE secteur IS NOT NULL AND secteur != '' ORDER BY secteur"
                ).fetchall()]
        elif isinstance(sectors, str):
            sectors = [sectors]
        elif not isinstance(sectors, list):
            return jsonify({"error": "sectors doit être une liste ou une chaîne"}), 400

        sectors = [s.strip() for s in sectors if isinstance(s, str) and s.strip()]
        if not sectors:
            return jsonify({"error": "Aucun secteur valide fourni"}), 400

        created_lists = []
        skipped = []
        with get_conn() as conn:
            for sector in sectors:
                lead_ids = _get_uncontacted_lead_ids(conn, sector)
                if not lead_ids:
                    skipped.append({"sector": sector, "reason": "aucun lead non contacté trouvé"})
                    continue

                batches = _chunked(lead_ids, batch_size)
                total_batches = len(batches)
                sector_label = _human_sector_name(sector)
                icon = _SECTOR_ICONS.get(sector, "📋")

                for index, batch in enumerate(batches, start=1):
                    if total_batches == 1:
                        list_name = f"{sector_label} — {len(batch)} leads non contactés"
                    else:
                        list_name = f"{sector_label} — {len(batch)} leads non contactés ({index}/{total_batches})"
                    description = (
                        f"Leads du secteur {sector_label}, non contactés. "
                        f"Batch {index}/{total_batches}."
                    )
                    list_id = _create_list_with_leads(conn, list_name, description, batch, icon=icon)
                    created_lists.append({
                        "sector": sector,
                        "sector_label": sector_label,
                        "list_id": list_id,
                        "nom": list_name,
                        "count": len(batch),
                        "batch": index,
                        "total_batches": total_batches,
                    })

        return jsonify({"success": True, "created": created_lists, "skipped": skipped}), 201
    except Exception as e:
        logger.error(f"api_lists_create_sector_batches → {e}")
        return jsonify({"error": str(e)}), 500



# ─── CRUD Listes ─────────────────────────────────────────────────────────────

@lists_bp.route("/api/lists", methods=["GET"])
def api_lists_get():
    """Retourne toutes les listes non archivées avec le nombre de leads dans chacune.
    Paramètre optionnel ?archived=1 pour lister les archivées."""
    try:
        show_archived = request.args.get("archived", "0") == "1"
        with get_conn() as conn:
            where = "WHERE ll.archived = 1" if show_archived else "WHERE ll.archived = 0"
            rows = conn.execute(f"""
                SELECT
                    ll.id, ll.nom, ll.description, ll.couleur, ll.icone,
                    ll.created_at, ll.updated_at,
                    ll.note, ll.contactee, ll.contacted_at,
                    ll.relance_j3, ll.relance_j7, ll.relance_j14,
                    ll.archived, ll.archived_at, ll.campaign_id,
                    COUNT(lli.lead_id) AS nb_leads
                FROM lead_lists ll
                LEFT JOIN lead_list_items lli ON lli.list_id = ll.id
                {where}
                GROUP BY ll.id
                ORDER BY ll.updated_at DESC
            """).fetchall()
        return jsonify({"lists": [dict(r) for r in rows]})
    except Exception as e:
        logger.error(f"api_lists_get → {e}")
        return jsonify({"error": str(e)}), 500


@lists_bp.route("/api/lists/<int:list_id>", methods=["GET"])
def api_lists_get_one(list_id):
    """Retourne les détails d'une liste spécifique."""
    try:
        with get_conn() as conn:
            row = conn.execute("""
                SELECT
                    ll.id, ll.nom, ll.description, ll.couleur, ll.icone,
                    ll.created_at, ll.updated_at,
                    ll.note, ll.contactee, ll.contacted_at,
                    ll.relance_j3, ll.relance_j7, ll.relance_j14,
                    ll.archived, ll.archived_at, ll.campaign_id,
                    COUNT(lli.lead_id) AS nb_leads
                FROM lead_lists ll
                LEFT JOIN lead_list_items lli ON lli.list_id = ll.id
                WHERE ll.id = ?
                GROUP BY ll.id
            """, (list_id,)).fetchone()
            if not row:
                return jsonify({"error": "Liste non trouvée"}), 404
        return jsonify({"list": dict(row)})
    except Exception as e:
        logger.error(f"api_lists_get_one({list_id}) → {e}")
        return jsonify({"error": str(e)}), 500


@lists_bp.route("/api/lists", methods=["POST"])
def api_lists_create():
    """Crée une nouvelle liste."""
    try:
        data = request.get_json() or {}
        nom = (data.get("nom") or "").strip()
        if not nom:
            return jsonify({"error": "nom requis"}), 400
        description = (data.get("description") or "").strip()
        couleur = (data.get("couleur") or "#6366f1").strip()
        icone = (data.get("icone") or "📋").strip()

        with get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO lead_lists (nom, description, couleur, icone) VALUES (?, ?, ?, ?)",
                (nom, description, couleur, icone)
            )
            conn.commit()
            list_id = cur.lastrowid
            row = conn.execute("SELECT * FROM lead_lists WHERE id = ?", (list_id,)).fetchone()
        return jsonify({"success": True, "list": dict(row)}), 201
    except Exception as e:
        logger.error(f"api_lists_create → {e}")
        return jsonify({"error": str(e)}), 500


@lists_bp.route("/api/lists/<int:list_id>", methods=["PUT"])
def api_lists_update(list_id):
    """Modifie les champs d'une liste (nom, description, couleur, icône, note, contactée, relances, archivage)."""
    try:
        data = request.get_json() or {}
        allowed = {"nom", "description", "couleur", "icone", "note",
                   "contactee", "relance_j3", "relance_j7", "relance_j14", "archived"}
        fields = {k: v for k, v in data.items() if k in allowed}
        if not fields:
            return jsonify({"error": "Aucun champ valide"}), 400

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        fields["updated_at"] = now

        # Gestion automatique des timestamps
        if "contactee" in fields:
            if fields["contactee"] == 1:
                fields["contacted_at"] = now
            else:
                fields["contacted_at"] = None
        if "archived" in fields:
            if fields["archived"] == 1:
                fields["archived_at"] = now
            else:
                fields["archived_at"] = None

        sets = ", ".join(f"{k}=?" for k in fields)
        values = list(fields.values()) + [list_id]

        with get_conn() as conn:
            cur = conn.execute(f"UPDATE lead_lists SET {sets} WHERE id=?", values)
            conn.commit()
            if cur.rowcount == 0:
                return jsonify({"error": "Liste non trouvée"}), 404
            row = conn.execute("SELECT * FROM lead_lists WHERE id=?", (list_id,)).fetchone()
        return jsonify({"success": True, "list": dict(row)})
    except Exception as e:
        logger.error(f"api_lists_update({list_id}) → {e}")
        return jsonify({"error": str(e)}), 500


@lists_bp.route("/api/lists/<int:list_id>", methods=["DELETE"])
def api_lists_delete(list_id):
    """Supprime une liste (les leads ne sont PAS supprimés)."""
    try:
        with get_conn() as conn:
            cur = conn.execute("DELETE FROM lead_lists WHERE id=?", (list_id,))
            conn.commit()
            if cur.rowcount == 0:
                return jsonify({"error": "Liste non trouvée"}), 404
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"api_lists_delete({list_id}) → {e}")
        return jsonify({"error": str(e)}), 500


# ─── Leads dans une liste ─────────────────────────────────────────────────────

@lists_bp.route("/api/lists/<int:list_id>/leads", methods=["GET"])
def api_list_leads(list_id):
    """Retourne les leads d'une liste, paginés."""
    try:
        page = max(1, int(request.args.get("page", 1)))
        limit = min(1000, max(1, int(request.args.get("limit", 50))))
        search = request.args.get("search", "").strip()
        offset = (page - 1) * limit

        with get_conn() as conn:
            # Vérifier que la liste existe
            lst = conn.execute("SELECT id, nom FROM lead_lists WHERE id=?", (list_id,)).fetchone()
            if not lst:
                return jsonify({"error": "Liste non trouvée"}), 404

            where_extra = ""
            params_extra = []
            if search:
                where_extra = " AND (LOWER(lb.nom) LIKE LOWER(?) OR LOWER(lb.site_web) LIKE LOWER(?))"
                params_extra = [f"%{search}%", f"%{search}%"]

            count = conn.execute(f"""
                SELECT COUNT(*) FROM lead_list_items lli
                JOIN leads_bruts lb ON lb.id = lli.lead_id
                WHERE lli.list_id = ? {where_extra}
            """, [list_id] + params_extra).fetchone()[0]

            rows = conn.execute(f"""
                SELECT
                    lb.id, lb.nom, lb.ville, lb.category, lb.source,
                    lb.email, lb.email_valide, lb.telephone, lb.site_web,
                    lb.statut, lb.rating, lb.nb_avis, lb.tag_urgence,
                    lb.date_scraping, lb.secteur,
                    la.id AS audit_id, la.mobile_score, la.score_urgence,
                    la.email_objet, la.email_corps, la.approuve,
                    la.lien_rapport, la.statut_prospection,
                    la.email_valide AS email_valide_audit,
                    la.ceo_prenom, la.ceo_nom,
                    lli.added_at
                FROM lead_list_items lli
                JOIN leads_bruts lb ON lb.id = lli.lead_id
                LEFT JOIN leads_audites la ON la.lead_id = lb.id
                WHERE lli.list_id = ? {where_extra}
                ORDER BY lli.added_at DESC
                LIMIT ? OFFSET ?
            """, [list_id] + params_extra + [limit, offset]).fetchall()

        total_pages = max(1, (count + limit - 1) // limit)
        return jsonify({
            "leads": [dict(r) for r in rows],
            "total": count,
            "page": page,
            "total_pages": total_pages,
            "list": dict(lst),
        })
    except Exception as e:
        logger.error(f"api_list_leads({list_id}) → {e}")
        return jsonify({"error": str(e)}), 500


@lists_bp.route("/api/lists/<int:list_id>/leads", methods=["POST"])
def api_list_add_leads(list_id):
    """Ajoute un ou plusieurs leads à une liste (idempotent — doublons ignorés)."""
    try:
        data = request.get_json() or {}
        lead_ids = data.get("lead_ids") or []
        if not lead_ids:
            return jsonify({"error": "lead_ids requis"}), 400

        with get_conn() as conn:
            lst = conn.execute("SELECT id FROM lead_lists WHERE id=?", (list_id,)).fetchone()
            if not lst:
                return jsonify({"error": "Liste non trouvée"}), 404

            added = 0
            already = 0
            for lid in lead_ids:
                try:
                    conn.execute(
                        "INSERT INTO lead_list_items (list_id, lead_id) VALUES (?, ?)",
                        (list_id, lid)
                    )
                    added += 1
                except Exception:
                    # UNIQUE constraint → déjà présent, on ignore
                    already += 1

            # Mettre à jour updated_at de la liste
            conn.execute(
                "UPDATE lead_lists SET updated_at=? WHERE id=?",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), list_id)
            )
            conn.commit()

        return jsonify({"success": True, "added": added, "already": already})
    except Exception as e:
        logger.error(f"api_list_add_leads({list_id}) → {e}")
        return jsonify({"error": str(e)}), 500


@lists_bp.route("/api/lists/<int:list_id>/leads", methods=["DELETE"])
def api_list_remove_leads(list_id):
    """Retire un ou plusieurs leads d'une liste (sans supprimer les leads)."""
    try:
        data = request.get_json() or {}
        lead_ids = data.get("lead_ids") or []
        if not lead_ids:
            return jsonify({"error": "lead_ids requis"}), 400

        with get_conn() as conn:
            removed = 0
            for lid in lead_ids:
                cur = conn.execute(
                    "DELETE FROM lead_list_items WHERE list_id=? AND lead_id=?",
                    (list_id, lid)
                )
                removed += cur.rowcount
            conn.execute(
                "UPDATE lead_lists SET updated_at=? WHERE id=?",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), list_id)
            )
            conn.commit()

        return jsonify({"success": True, "removed": removed})
    except Exception as e:
        logger.error(f"api_list_remove_leads({list_id}) → {e}")
        return jsonify({"error": str(e)}), 500


# ─── Listes d'un lead ─────────────────────────────────────────────────────────

@lists_bp.route("/api/leads/<int:lead_id>/lists", methods=["GET"])
def api_lead_lists(lead_id):
    """Retourne les listes auxquelles appartient un lead."""
    try:
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT ll.id, ll.nom, ll.couleur, ll.icone, lli.added_at
                FROM lead_list_items lli
                JOIN lead_lists ll ON ll.id = lli.list_id
                WHERE lli.lead_id = ?
                ORDER BY lli.added_at DESC
            """, (lead_id,)).fetchall()
        return jsonify({"lists": [dict(r) for r in rows]})
    except Exception as e:
        logger.error(f"api_lead_lists({lead_id}) → {e}")
        return jsonify({"error": str(e)}), 500


# ─── Actions groupées sur une liste ──────────────────────────────────────────

@lists_bp.route("/api/lists/<int:list_id>/actions", methods=["POST"])
def api_list_action(list_id):
    """
    Déclenche une action groupée sur tous les leads d'une liste.
    Actions disponibles : audit | find_emails | generate_emails | send_emails | export_csv
    """
    try:
        data = request.get_json() or {}
        action = (data.get("action") or "").strip()
        if not action:
            return jsonify({"error": "action requise"}), 400

        # Récupérer les IDs des leads de cette liste
        with get_conn() as conn:
            lst = conn.execute("SELECT id, nom FROM lead_lists WHERE id=?", (list_id,)).fetchone()
            if not lst:
                return jsonify({"error": "Liste non trouvée"}), 404
            rows = conn.execute(
                "SELECT lead_id FROM lead_list_items WHERE list_id=?", (list_id,)
            ).fetchall()

        lead_ids = [r["lead_id"] for r in rows]
        if not lead_ids:
            return jsonify({"error": "La liste est vide"}), 400

        list_nom = lst["nom"]

        # ── Export CSV ─────────────────────────────────────────────────────
        if action == "export_csv":
            with get_conn() as conn:
                rows = conn.execute("""
                    SELECT
                        lb.id, lb.nom, lb.ville, lb.category, lb.source,
                        lb.email, lb.email_valide, lb.telephone, lb.site_web,
                        lb.statut, lb.rating, lb.nb_avis,
                        la.mobile_score, la.score_urgence, la.probleme_principal,
                        la.email_objet, la.statut_prospection
                    FROM lead_list_items lli
                    JOIN leads_bruts lb ON lb.id = lli.lead_id
                    LEFT JOIN leads_audites la ON la.lead_id = lb.id
                    WHERE lli.list_id = ?
                    ORDER BY lli.added_at DESC
                """, (list_id,)).fetchall()

            output = io.StringIO()
            fieldnames = [
                "id", "nom", "ville", "category", "source",
                "email", "email_valide", "telephone", "site_web",
                "statut", "rating", "nb_avis",
                "mobile_score", "score_urgence", "probleme_principal",
                "email_objet", "statut_prospection"
            ]
            writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))

            filename_safe = f"liste_{list_nom}_{datetime.now().strftime('%Y%m%d')}.csv".replace(" ", "_")
            return Response(
                "\ufeff" + output.getvalue(),          # BOM UTF-8 pour Excel
                mimetype="text/csv; charset=utf-8",
                headers={
                    "Content-Disposition": f"attachment; filename={filename_safe}",
                    "Content-Type": "text/csv; charset=utf-8",
                }
            )

        # ── Actions déléguées aux routes Flask existantes ──────────────────
        # On construit le payload et on appelle les routes existantes
        # via flask.current_app pour réutiliser exactement la même logique.
        DELEGATED = {
            "audit":          ("/api/audit/launch",       {"lead_ids": lead_ids}),
            "find_emails":    ("/api/leads/find-emails",  {"lead_ids": lead_ids}),
            "generate_emails":("/api/email/generate",     {"lead_ids": lead_ids}),
            "send_emails":    ("/api/email/send-approved", {}),
        }
        if action not in DELEGATED:
            return jsonify({"error": f"Action inconnue : {action}"}), 400

        url, payload = DELEGATED[action]
        payload["lead_ids"] = lead_ids  # toujours passer les ids

        from flask import current_app
        with current_app.test_client() as client:
            resp = client.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            try:
                data = resp.get_json() or {}
            except Exception:
                data = {}

        status_ok = resp.status_code < 400
        return jsonify({
            "success": status_ok,
            "action": action,
            "lead_count": len(lead_ids),
            "message": data.get("message") or (
                f"Action « {action} » lancée pour {len(lead_ids)} leads de « {list_nom} »"
                if status_ok else data.get("error", "Erreur inconnue")
            ),
            **{k: v for k, v in data.items() if k not in ("message", "error")},
        }), resp.status_code if not status_ok else 202

    except Exception as e:
        logger.error(f"api_list_action({list_id}, {action}) → {e}")
        return jsonify({"error": str(e)}), 500
