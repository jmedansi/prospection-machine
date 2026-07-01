# -*- coding: utf-8 -*-
"""
dashboard/routes/leads.py — Routes API leads

Couche HTTP mince : valide les paramètres, délègue aux repos/agents,
retourne JSON. Pas de logique métier ici.
"""
from flask import Blueprint, jsonify, request
from database.repos import leads_repo
from database.connection import get_conn

leads_bp = Blueprint("leads", __name__)

# ─── Statuts display unifiés ──────────────────────────────────────────────────

_SNIPER_SOURCES = {"ads", "fb_ads", "transparency", "ecom", "tech", "jobs", "bodacc"}

_STATUT_MAP = {
    # Maps
    ("maps", "en_attente"):    ("À traiter",      "#9ca3af"),
    ("maps", "scrape"):        ("À traiter",      "#9ca3af"),
    ("maps", "audite"):        ("Audité",          "#3b82f6"),
    ("maps", "email_genere"):  ("Email prêt",      "#6366f1"),
    ("maps", "scheduled"):     ("Programmé",       "#8b5cf6"),
    ("maps", "envoye"):        ("Envoyé",          "#8b5cf6"),
    ("maps", "contacte"):      ("Contacté",        "#60a5fa"),
    ("maps", "repondu"):       ("Répondu",         "#f59e0b"),
    ("maps", "bounced"):       ("Bounced",         "#ef4444"),
    ("maps", "archive"):       ("Archivé",         "#6b7280"),
    # Sniper
    ("sniper", "a_contacter"):      ("À contacter",   "#9ca3af"),
    ("sniper", "en_attente"):       ("À contacter",   "#9ca3af"),
    ("sniper", "contacte"):         ("Contacté",      "#60a5fa"),
    ("sniper", "email_genere"):     ("Email prêt",    "#6366f1"),
    ("sniper", "step1_envoye"):     ("Step 1 envoyé", "#3b82f6"),
    ("sniper", "repondu"):          ("Répondu ✓",     "#f59e0b"),
    ("sniper", "lien_envoye"):      ("Rapport livré", "#10b981"),
    ("sniper", "linkedin_envoye"):  ("LinkedIn",      "#0077b5"),
    ("sniper", "formulaire_envoye"):("Formulaire",    "#6366f1"),
    ("sniper", "whatsapp_envoye"):  ("WhatsApp",      "#25d366"),
}


def _pipeline(source: str) -> str:
    return "sniper" if source in _SNIPER_SOURCES else "maps"


def _statut_display(statut_bruts: str, statut_pros: str, pipeline: str) -> dict:
    key = (pipeline, statut_pros or statut_bruts or "")
    label, color = _STATUT_MAP.get(key, ("?", "#9ca3af"))
    return {"label": label, "color": color}


def _normalize_unified(r: dict) -> dict:
    source   = r.get("source") or "maps"
    pipeline = _pipeline(source)
    statut_b = r.get("statut") or ""
    statut_p = r.get("statut_prospection") or ""
    return {
        "id":                 r["id"],
        "nom":                r.get("nom") or "",
        "notes":              r.get("notes") or "",
        "site_web":           r.get("site_web") or "",
        "source":             source,
        "pipeline":           pipeline,
        "ville":              r.get("ville") or "",
        "category":           r.get("category") or "",
        "email":              r.get("email") or "",
        "email_2":            r.get("email_2") or "",
        "email_valide":       r.get("email_valide") or "",
        "telephone":          r.get("telephone") or "",
        "telephone_2":        r.get("telephone_2") or "",
        "ceo_prenom":         r.get("ceo_prenom") or "",
        "ceo_nom":            r.get("ceo_nom") or "",
        "ceo_source":         r.get("ceo_source") or "",
        "score_mobile":       r.get("mobile_score") or 0,
        "rating":             r.get("rating") or 0,
        "nb_avis":            r.get("nb_avis") or 0,
        "tag_urgence":        r.get("tag_urgence") or "",
        "statut":             statut_b,
        "statut_prospection": statut_p,
        "statut_display":     _statut_display(statut_b, statut_p, pipeline),
        "audit_id":           r.get("audit_id"),
        "lien_rapport":       r.get("lien_rapport") or "",
        "approuve":           r.get("approuve") or 0,
        "score_urgence":      r.get("score_urgence") or 0,
        "copywriting_mode":   r.get("copywriting_mode") or "transfert",
        "is_catch_all":       bool(r.get("is_catch_all")),
        "date_scraping":      r.get("date_scraping") or "",
        "donnees_audit":      r.get("donnees_audit"),
    }


# ─── Endpoint unifié ──────────────────────────────────────────────────────────

@leads_bp.route("/api/leads/all")
def api_leads_all():
    """Liste paginée unifiée — délègue au repo centralisé."""
    try:
        source = request.args.get("source", "tous")
        statut = request.args.get("statut", "tous")
        tag    = request.args.get("tag", "")
        site_filter  = request.args.get("site_filter", "tous")
        email_filter = request.args.get("email_filter", "tous")
        search = request.args.get("search", "").strip()
        page   = max(1, int(request.args.get("page", 1)))
        limit  = min(10000, max(1, int(request.args.get("limit", 50))))
        campaign_id = request.args.get("campaign_id")
        if campaign_id in ("null", "undefined"): campaign_id = None

        score_filter = request.args.get("score_filter", "tous")
        notes_filter = request.args.get("notes_filter", "tous")
        sector_filter = request.args.get("sector", "tous")
        list_id_filter = request.args.get("list_id", type=int)
        # Mapping propre pour éviter le bug "without" -> "avecout"
        filter_map = {"sans": "sans", "tous": "tous",
                      "responsables": "responsables", "infos": "infos",
                      "partiel": "partiel"}
        
        result = leads_repo.get_all(
            statut=statut,
            limit=limit,
            page=page,
            site=filter_map.get(site_filter, "tous"),
            email=filter_map.get(email_filter, "tous"),
            sector=sector_filter,
            search=search,
            campaign_id=int(campaign_id) if campaign_id else None,
            source=source,
            tag=tag,
            score=score_filter,
            notes=filter_map.get(notes_filter, "tous"),
            list_id=list_id_filter,
        )
        return jsonify(result)
    except Exception as e:
        logger.error(f"api_leads_all error: {e}")
        return jsonify({"error": str(e)}), 500


@leads_bp.route("/api/leads/<int:lead_id>/status", methods=["PUT"])
def api_lead_update_status(lead_id):
    """Met à jour le statut d'un lead (Kanban)."""
    try:
        data = request.get_json() or {}
        new_status = data.get("status")
        if not new_status:
            return jsonify({"error": "status requis"}), 400
        
        ok = leads_repo.update_status_unified(lead_id, new_status)
        return jsonify({"success": ok})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@leads_bp.route("/api/leads/<int:lead_id>/edit", methods=["PUT"])
def api_lead_edit(lead_id):
    """
    Édition unifiée d'un lead — met à jour leads_bruts ET leads_audites.
    Accepte : nom, email, telephone, site_web, category, ville,
              ceo_prenom, ceo_nom (→ leads_audites)
    """
    try:
        data = request.get_json() or {}

        bruts_allowed  = {"nom", "email", "email_2", "telephone", "telephone_2",
                          "site_web", "category", "ville", "notes"}
        audits_allowed = {"ceo_prenom", "ceo_nom"}

        bruts_data  = {k: v for k, v in data.items() if k in bruts_allowed}
        audits_data = {k: v for k, v in data.items() if k in audits_allowed}

        if "email" in bruts_data:
            audits_data["email_valide"] = bruts_data["email"]
            bruts_data["email_valide"] = bruts_data["email"]

        with get_conn() as conn:
            if bruts_data:
                sets = ", ".join(f"{k}=?" for k in bruts_data)
                conn.execute(
                    f"UPDATE leads_bruts SET {sets} WHERE id=?",
                    list(bruts_data.values()) + [lead_id]
                )
            if audits_data:
                sets = ", ".join(f"{k}=?" for k in audits_data)
                conn.execute(
                    f"UPDATE leads_audites SET {sets} WHERE lead_id=?",
                    list(audits_data.values()) + [lead_id]
                )
            conn.commit()

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@leads_bp.route("/api/sources/stats")
def api_sources_stats():
    """Retourne le nombre de leads par source pour le hub Sources."""
    try:
        campaign_id = request.args.get("campaign_id")
        if campaign_id in ("null", "undefined", ""):
            campaign_id = None
        with get_conn() as conn:
            where = "WHERE statut NOT IN ('archive', 'desabonne')"
            params = []
            if campaign_id:
                where += " AND campaign_id = ?"
                params.append(int(campaign_id))
            rows = conn.execute(f"""
                SELECT
                    CASE
                        WHEN source IN ('ads','fb_ads','transparency') THEN source
                        WHEN source IN ('tech','ecom')                 THEN 'tech'
                        WHEN source = 'jobs'                           THEN 'jobs'
                        WHEN source = 'bodacc'                         THEN 'bodacc'
                        ELSE 'maps'
                    END AS src,
                    COUNT(*) AS n
                FROM leads_bruts
                {where}
                GROUP BY src
            """, params).fetchall()
        stats = {r[0]: r[1] for r in rows}
        return jsonify({"stats": stats})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@leads_bp.route("/api/leads/sectors")
@leads_bp.route("/api/sectors")
def api_leads_sectors():
    """Retourne la liste des secteurs distincts présents en base."""
    try:
        from database import get_conn
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT secteur FROM leads_bruts WHERE secteur IS NOT NULL AND secteur != '' ORDER BY secteur"
            ).fetchall()
        label_map = {
            "immobilier": "Immobilier",
            "courtage": "Courtage",
            "concessionnaires_auto": "Concessionnaires Auto",
            "cliniques_esthetiques": "Cliniques Esthétiques",
            "ecoles_formation": "Écoles / Formation",
        }
        sectors = [{"value": r[0], "label": label_map.get(r[0], r[0])} for r in rows]
        return jsonify({"sectors": sectors})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@leads_bp.route("/api/leads/batch-delete", methods=["POST"])
@leads_bp.route("/api/leads/delete_batch", methods=["POST"])
def api_leads_batch_delete():
    """Supprime un lot de leads par leurs IDs ou leurs noms."""
    try:
        data  = request.get_json() or {}
        ids   = data.get("ids") or data.get("lead_ids")
        noms  = data.get("noms") or data.get("lead_names")
        from database import get_conn
        deleted = 0
        with get_conn() as conn:
            if ids:
                for lid in ids:
                    conn.execute("DELETE FROM leads_bruts WHERE id=?", (lid,))
                    deleted += 1
            elif noms:
                for nom in noms:
                    conn.execute("DELETE FROM leads_bruts WHERE nom=?", (nom,))
                    deleted += 1
            conn.commit()
        return jsonify({"success": True, "deleted": deleted})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@leads_bp.route("/api/leads/purge-zero-avis", methods=["POST"])
def api_leads_purge_zero_avis():
    """Supprime les leads non encore contactés avec 0 avis."""
    try:
        from database import get_conn
        with get_conn() as conn:
            cur = conn.execute(
                "DELETE FROM leads_bruts WHERE nb_avis = 0 AND statut IN ('scraped', 'en_attente')"
            )
            conn.commit()
        return jsonify({"success": True, "deleted": cur.rowcount})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@leads_bp.route("/api/leads")
def api_leads():
    """Liste paginée de leads avec filtres."""
    try:
        campaign_id  = request.args.get("campaign_id", type=int)
        campaign_ids = request.args.get("campaign_ids")
        list_id      = request.args.get("list_id", type=int)
        result = leads_repo.get_all(
            statut=request.args.get("statut", "tous"),
            site=request.args.get("site", "tous"),
            email=request.args.get("email", "tous"),
            sector=request.args.get("sector", "tous"),
            search=request.args.get("search", "").strip(),
            campaign_id=campaign_id,
            campaign_ids=[int(x) for x in campaign_ids.split(",") if x.strip().isdigit()] if campaign_ids else None,
            date_start=request.args.get("date_start"),
            date_end=request.args.get("date_end"),
            page=int(request.args.get("page", 1)),
            limit=int(request.args.get("limit", 50)),
            list_id=list_id,
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@leads_bp.route("/api/leads/<int:lead_id>")
def api_lead_by_id(lead_id):
    """Retourne un lead complet (bruts + audit jointure)."""
    version = int(request.args.get("v", 4))
    lead = leads_repo.get_by_id(lead_id, version=version)
    if not lead:
        return jsonify({"error": "Lead non trouvé"}), 404
    return jsonify({"lead": lead})


@leads_bp.route("/api/leads/<int:lead_id>/contact", methods=["PUT"])
def api_lead_update_contact(lead_id):
    """Met à jour les moyens de contact (mail, wp, li, fb, appel, autres)."""
    try:
        data = request.get_json() or {}
        if not data:
            return jsonify({"error": "body requis"}), 400
        contact_map = {}
        for method in ("mail", "wp", "li", "fb", "appel", "autres"):
            key = f"contact_{method}"
            if key in data:
                contact_map[key] = 1 if data[key] else 0
        if not contact_map:
            return jsonify({"error": "Aucun champ contact_* valide"}), 400
        ok = leads_repo.update_fields(lead_id, contact_map)
        if not ok:
            return jsonify({"error": "Échec mise à jour"}), 500
        # Lire l'état réel en DB pour déterminer le statut
        with get_conn() as conn:
            row = conn.execute(
                "SELECT contact_mail, contact_wp, contact_li, contact_fb, contact_appel, contact_autres FROM leads_audites WHERE lead_id=?",
                (lead_id,)
            ).fetchone()
        any_checked = row and any(v == 1 for v in row)
        new_statut = "contacte" if any_checked else "a_contacter"
        leads_repo.update_fields(lead_id, {"statut_prospection": new_statut})
        return jsonify({"success": True, **contact_map, "statut_prospection": new_statut})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@leads_bp.route("/api/lead/update", methods=["PUT"])
def api_lead_update():
    """Met à jour des champs d'un lead."""
    try:
        data = request.get_json() or {}
        lead_id = data.get("id")
        if not lead_id:
            return jsonify({"error": "id requis"}), 400
        ok = leads_repo.update_fields(lead_id, data)
        if not ok:
            return jsonify({"error": "Aucun champ valide à mettre à jour"}), 400
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@leads_bp.route("/api/leads/find-emails", methods=["POST"])
def api_leads_bulk_find_emails():
    """Lance la recherche d'email en masse (Enrichissement)."""
    try:
        from agents.enrichisseur.agent import enrichisseur_agent
        data = request.get_json() or {}
        lead_ids = data.get("lead_ids") or data.get("ids", [])
        if not lead_ids:
            return jsonify({"error": "lead_ids requis"}), 400
        
        result = enrichisseur_agent.run(lead_ids=lead_ids)
        if not result.success:
            return jsonify({"error": result.error}), 409
            
        return jsonify({"success": True, **result.data})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@leads_bp.route("/api/leads/enrich/status")
def api_enrich_status():
    """Retourne l'état courant de la recherche d'emails."""
    from agents.enrichisseur.agent import enrichisseur_agent
    return jsonify(enrichisseur_agent.status())


@leads_bp.route("/api/leads/enrich/stop", methods=["POST"])
def api_enrich_stop():
    """Arrête la recherche d'emails en cours."""
    from agents.enrichisseur.agent import enrichisseur_agent
    enrichisseur_agent.stop()
    return jsonify({"success": True, "message": "Recherche emails arrêtée"})


@leads_bp.route("/api/leads/<int:lead_id>/find-email", methods=["POST"])
def api_leads_find_email(lead_id: int):
    """Relance manuelle de la recherche d'email pour un lead specifique."""
    try:
        from agents.enrichisseur.agent import enrichisseur_agent
        result = enrichisseur_agent.run(lead_id=lead_id)
        if result.success:
            return jsonify({"success": True, "lead_id": lead_id, "data": result.data})
        else:
            return jsonify({"error": result.error}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@leads_bp.route("/api/lead/delete", methods=["DELETE"])
def api_lead_delete():
    """Supprime un lead."""
    try:
        lead_id = request.args.get("id", type=int)
        if not lead_id:
            return jsonify({"error": "id requis"}), 400
        ok = leads_repo.delete(lead_id)
        if not ok:
            return jsonify({"error": "Lead non trouvé"}), 404
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@leads_bp.route("/api/leads/<int:lead_id>/regenerate-email-stream", methods=["POST"])
def api_regenerate_email_stream(lead_id):
    """Régénère un email avec streaming (SSE)."""
    from flask import Response, stream_with_context
    from services.email_generator import generate_email_for_lead

    def generate():
        try:
            # Générer l'email
            ok = generate_email_for_lead(lead_id)
            if not ok:
                yield "data: {\"error\": \"Échec génération\"}\n\n"
                return

            # Retrieve generated email
            from database.repos import leads_repo
            lead = leads_repo.get_by_id(lead_id)
            if not lead:
                yield "data: {\"error\": \"Lead non trouvé\"}\n\n"
                return

            objet = lead.get('email_objet', '')
            corps = lead.get('email_corps', '')

            # Streaming avec chunks
            chunk_size = 50
            for i in range(0, len(corps), chunk_size):
                chunk = corps[i:i+chunk_size]
                yield f"data: {{\"corps\": \"{chunk.replace('\"', '\\\"')}\", \"objet\": \"{objet.replace('\"', '\\\"')}\"}}\n\n"

            yield "data: {\"done\": true, \"corps\": \"\"}\n\n"

        except Exception as e:
            yield f"data: {{\"error\": \"{str(e)}\"}}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')
