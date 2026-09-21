# -*- coding: utf-8 -*-
"""
dashboard/routes/emails.py — Routes API emails

P0 fixes :
  - POST /api/email/send-approved  (alias de /api/email/send)
  - POST /api/email/test           (envoi email de test)
"""
import os
from flask import Blueprint, jsonify, request
from agents.redacteur  import redacteur_agent
from agents.expediteur import expediteur_agent
from agents.tracker    import tracker_agent
from database import get_conn
from database.repos import audits_repo, leads_repo

emails_bp = Blueprint("emails", __name__)


@emails_bp.route("/api/email/generate", methods=["POST"])
def api_email_generate():
    data     = request.get_json() or {}
    lead_ids = data.get("lead_ids", [])
    if not lead_ids:
        return jsonify({"error": "lead_ids requis"}), 400
    result = redacteur_agent.run(lead_ids)
    if not result:
        err = getattr(result, "error", "Erreur génération")
        return jsonify({"error": err}), 500
    return jsonify({"success": True, **result.data})


@emails_bp.route("/api/email/send", methods=["POST"])
@emails_bp.route("/api/email/send-approved", methods=["POST"])
def api_email_send():
    data     = request.get_json() or {}
    lead_ids = data.get("lead_ids")   # None = tous les approuvés
    result   = expediteur_agent.run(lead_ids=lead_ids)
    if not result:
        err = getattr(result, "error", "Erreur envoi")
        return jsonify({"error": err}), 400
    return jsonify({"statut": "lance", **result.data})


@emails_bp.route("/api/email/cancel", methods=["POST"])
def api_email_cancel():
    """Annule l'envoi en cours."""
    from services.job_tracker import _email_job
    _email_job["cancelled"] = True
    return jsonify({"success": True, "message": "Envoi annulé"})


@emails_bp.route("/api/email/status")
def api_email_status():
    return jsonify(expediteur_agent.status())


@emails_bp.route("/api/email/test", methods=["POST"])
def api_email_test():
    """Envoie un email de test à l'adresse configurée (ou celle fournie)."""
    data    = request.get_json() or {}
    lead_id = data.get("lead_id")
    to      = data.get("to") or os.getenv("RESEND_SENDER_EMAIL") or os.getenv("BREVO_SENDER_EMAIL")

    if not lead_id:
        return jsonify({"error": "lead_id requis"}), 400
    if not to:
        return jsonify({"error": "Adresse de test introuvable (fournir 'to' ou configurer RESEND_SENDER_EMAIL)"}), 400

    result = expediteur_agent.send_test(lead_id=lead_id, to_email=to)
    if not result:
        err = getattr(result, "error", "Erreur envoi test")
        return jsonify({"error": err}), 500
    return jsonify({"success": True, **result.data})


@emails_bp.route("/api/emails", methods=["GET"])
def api_emails_list():
    """Liste les emails envoyés avec leurs stats de tracking."""
    try:
        from database import get_conn
        statut  = request.args.get("statut")        # opened/clicked/replied/bounce
        list_id = request.args.get("list_id", type=int)
        limit   = int(request.args.get("limit", 50))
        page    = int(request.args.get("page", 1))
        offset  = (page - 1) * limit

        where, params = [], []
        if statut == "opened":   where.append("ee.ouvert = 1")
        elif statut == "clicked": where.append("ee.clique = 1")
        elif statut == "replied": where.append("ee.repondu = 1")
        elif statut == "bounce":  where.append("ee.bounce = 1")
        elif statut == "spam":    where.append("ee.spam = 1")

        if list_id:
            where.append("ee.lead_id IN (SELECT lead_id FROM lead_list_items WHERE list_id = ?)")
            params.append(list_id)

        where_sql = "WHERE " + " AND ".join(where) if where else ""
        with get_conn() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM emails_envoyes ee {where_sql}", params
            ).fetchone()[0]
            rows = conn.execute(f"""
                SELECT ee.id, ee.lead_id, lb.nom, lb.ville, lb.category as secteur,
                       ee.email_destinataire, ee.email_objet, ee.date_envoi,
                       ee.ouvert, ee.clique, ee.repondu, ee.bounce, ee.spam,
                       ee.rdv_confirme, ee.statut_envoi
                FROM emails_envoyes ee
                LEFT JOIN leads_bruts lb ON ee.lead_id = lb.id
                {where_sql}
                ORDER BY ee.date_envoi DESC
                LIMIT ? OFFSET ?
            """, params + [limit, offset]).fetchall()

        return jsonify({
            "emails": [dict(r) for r in rows],
            "total": total,
            "page": page
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@emails_bp.route("/api/email/update", methods=["POST"])
def api_email_update():
    data    = request.get_json() or {}
    lead_id = data.get("lead_id")
    if not lead_id:
        return jsonify({"error": "lead_id requis"}), 400
    ok = audits_repo.update_email_content(
        lead_id, data.get("objet", ""), data.get("corps", "")
    )
    return jsonify({"success": ok})


@emails_bp.route("/api/email/approve", methods=["POST"])
def api_email_approve():
    data    = request.get_json() or {}
    lead_id = data.get("lead_id")
    if not lead_id:
        return jsonify({"error": "lead_id requis"}), 400
    ok = audits_repo.set_approval(lead_id, True)
    return jsonify({"success": ok})


@emails_bp.route("/api/email/disapprove", methods=["POST"])
def api_email_disapprove():
    data    = request.get_json() or {}
    lead_id = data.get("lead_id")
    if not lead_id:
        return jsonify({"error": "lead_id requis"}), 400
    ok = audits_repo.set_approval(lead_id, False)
    return jsonify({"success": ok})


@emails_bp.route("/api/emails/<int:email_id>")
def api_email_by_id(email_id):
    """Retourne un email envoyé avec les infos du prospect (pour le CRM)."""
    try:
        from database import get_conn
        with get_conn() as conn:
            row = conn.execute("""
                SELECT ee.id, ee.lead_id, ee.email_destinataire, ee.email_objet,
                       ee.email_corps, ee.date_envoi, ee.ouvert, ee.clique,
                       ee.repondu, ee.bounce, ee.spam, ee.rdv_confirme,
                       ee.statut_envoi, ee.notes,
                       lb.nom AS prospect_nom, lb.email AS prospect_email,
                       lb.ville, lb.telephone
                FROM emails_envoyes ee
                LEFT JOIN leads_bruts lb ON ee.lead_id = lb.id
                WHERE ee.id = ?
            """, (email_id,)).fetchone()
        if not row:
            return jsonify({"error": "Email non trouvé"}), 404
        return jsonify(dict(row))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@emails_bp.route("/api/crm/update", methods=["POST"])
def api_crm_update():
    """Met à jour les notes CRM d'un email envoyé."""
    try:
        from database import get_conn
        data     = request.get_json() or {}
        email_id = data.get("email_id")
        notes    = data.get("notes", "")
        if not email_id:
            return jsonify({"error": "email_id requis"}), 400
        with get_conn() as conn:
            conn.execute(
                "UPDATE emails_envoyes SET notes = ? WHERE id = ?",
                (notes, email_id)
            )
            conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@emails_bp.route("/api/crm/manual_contact", methods=["POST"])
def api_crm_manual_contact():
    try:
        data = request.get_json() or {}
        lead_id = data.get("lead_id")
        channel = data.get("channel", "Email")
        if not lead_id:
            return jsonify({"error": "lead_id requis"}), 400

        with get_conn() as conn:
            lead = conn.execute(
                "SELECT source, email FROM leads_bruts WHERE id = ?",
                (lead_id,)
            ).fetchone()
            if not lead:
                return jsonify({"error": "Lead introuvable"}), 404

            # Marquer le lead comme contacté
            leads_repo.update_status_unified(lead_id, "contacte")

            conn.execute("""
                INSERT INTO emails_envoyes (lead_id, email_destinataire, email_objet, email_corps, statut_envoi, date_envoi)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
            """, (
                lead_id,
                lead["email"] or "",
                f"Contact manuel via {channel}",
                f"Contact manuel enregistré via {channel}.",
                channel
            ))
            conn.commit()

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@emails_bp.route("/api/crm", methods=["GET"])
def api_crm_list():
    """Liste les emails envoyés avec filtres CRM."""
    try:
        from database import get_conn
        filter_type = request.args.get("filter", "tous")
        list_id = request.args.get("list_id", type=int)
        limit = int(request.args.get("limit", 50))
        page = int(request.args.get("page", 1))
        offset = (page - 1) * limit

        where_clauses = ["1=1"]
        params = []

        if filter_type == "ouverts":
            where_clauses.append("ee.ouvert = 1")
        elif filter_type == "cliques":
            where_clauses.append("ee.clique = 1")
        elif filter_type == "repondus":
            where_clauses.append("ee.repondu = 1")
        elif filter_type == "positifs":
            where_clauses.append("ee.repondu = 1 AND ee.rdv_confirme = 1")
        elif filter_type == "bounces":
            where_clauses.append("ee.bounce = 1")
        elif filter_type == "spam":
            where_clauses.append("ee.spam = 1")

        if list_id:
            where_clauses.append("ee.lead_id IN (SELECT lead_id FROM lead_list_items WHERE list_id = ?)")
            params.append(list_id)

        where_sql = " AND ".join(where_clauses)

        with get_conn() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM emails_envoyes ee WHERE {where_sql}",
                params
            ).fetchone()[0]

            rows = conn.execute(f"""
                SELECT ee.id, ee.lead_id, lb.nom, lb.ville, lb.category,
                       ee.email_destinataire, ee.email_objet, ee.date_envoi,
                       ee.ouvert, ee.clique, ee.repondu, ee.bounce, ee.spam,
                       ee.rdv_confirme, ee.statut_envoi, ee.notes
                FROM emails_envoyes ee
                LEFT JOIN leads_bruts lb ON ee.lead_id = lb.id
                WHERE {where_sql}
                ORDER BY ee.date_envoi DESC
                LIMIT ? OFFSET ?
            """, params + [limit, offset]).fetchall()

        return jsonify({
            "crm": [dict(r) for r in rows],
            "emails": [dict(r) for r in rows],  # alias pour compatibilité
            "total": total,
            "page": page,
            "total_pages": max(1, (total + limit - 1) // limit)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@emails_bp.route("/api/crm/counts")
def api_crm_counts():
    """Retourne les compteurs CRM pour le dashboard."""
    try:
        from database import get_conn
        with get_conn() as conn:
            stats = conn.execute("""
                SELECT
                    COUNT(*) as total_envoyes,
                    SUM(CASE WHEN ouvert = 1 THEN 1 ELSE 0 END) as total_ouverts,
                    SUM(CASE WHEN clique = 1 THEN 1 ELSE 0 END) as total_cliques,
                    SUM(CASE WHEN repondu = 1 THEN 1 ELSE 0 END) as total_repondus,
                    SUM(CASE WHEN rdv_confirme = 1 THEN 1 ELSE 0 END) as total_rdv,
                    SUM(CASE WHEN bounce = 1 THEN 1 ELSE 0 END) as total_bounces,
                    SUM(CASE WHEN spam = 1 THEN 1 ELSE 0 END) as total_spam
                FROM emails_envoyes
            """).fetchone()

        total = stats["total_envoyes"] or 1  # éviter division par zéro
        return jsonify({
            "envoyes": stats["total_envoyes"] or 0,
            "ouverts": stats["total_ouverts"] or 0,
            "cliques": stats["total_cliques"] or 0,
            "repondus": stats["total_repondus"] or 0,
            "rdv": stats["total_rdv"] or 0,
            "bounces": stats["total_bounces"] or 0,
            "spam": stats["total_spam"] or 0,
            "taux_ouverture": round((stats["total_ouverts"] or 0) * 100 / total, 1),
            "taux_clic": round((stats["total_cliques"] or 0) * 100 / total, 1),
            "taux_reponse": round((stats["total_repondus"] or 0) * 100 / total, 1)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@emails_bp.route("/api/tracking")
def api_tracking_list():
    """Liste les événements de tracking email."""
    try:
        from database import get_conn
        limit = int(request.args.get("limit", 50))

        with get_conn() as conn:
            rows = conn.execute("""
                SELECT
                    ee.id, ee.lead_id, lb.nom, ee.email_destinataire,
                    ee.email_objet, ee.date_envoi, ee.date_ouverture,
                    ee.date_clic, ee.ouvert, ee.clique, ee.repondu,
                    ee.statut_envoi
                FROM emails_envoyes ee
                LEFT JOIN leads_bruts lb ON ee.lead_id = lb.id
                WHERE ee.ouvert = 1 OR ee.clique = 1 OR ee.repondu = 1
                ORDER BY ee.date_envoi DESC
                LIMIT ?
            """, (limit,)).fetchall()

        # Format pour le frontend
        events = []
        for r in rows:
            row_dict = dict(r)
            if row_dict.get("ouvert"):
                events.append({
                    "nom": row_dict.get("nom", "—"),
                    "event": "ouvert",
                    "date": row_dict.get("date_ouverture") or row_dict.get("date_envoi")
                })
            if row_dict.get("clique"):
                events.append({
                    "nom": row_dict.get("nom", "—"),
                    "event": "cliqué",
                    "date": row_dict.get("date_clic") or row_dict.get("date_envoi")
                })
            if row_dict.get("repondu"):
                events.append({
                    "nom": row_dict.get("nom", "—"),
                    "event": "répondu",
                    "date": row_dict.get("date_envoi")
                })

        return jsonify({"tracking": events, "events": events})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@emails_bp.route("/api/sequences")
def api_sequences_list():
    """
    Vue complète des séquences de relances par lead.
    Retourne pour chaque lead : email initial + statut de chaque relance.
    """
    try:
        with get_conn() as conn:
            # Grouper toutes les séquences par lead_id (leads_audites.id)
            rows = conn.execute("""
                SELECT
                    seq.lead_id      AS la_id,
                    lb.nom,
                    lb.ville,
                    lb.category,
                    ee_init.email_destinataire AS email,
                    ee_init.date_envoi         AS date_email_initial,
                    seq.id                     AS seq_id,
                    seq.email_type,
                    seq.statut                 AS seq_statut,
                    seq.date_planifiee,
                    seq.date_envoi             AS seq_date_envoi
                FROM email_sequences seq
                JOIN leads_audites la   ON la.id  = seq.lead_id
                JOIN leads_bruts   lb   ON lb.id  = la.lead_id
                JOIN emails_envoyes ee_init ON ee_init.id = seq.email_record_id
                ORDER BY la.id, seq.email_type
            """).fetchall()

        # Pivot : un objet par lead avec ses 3 relances
        leads = {}
        for r in rows:
            la_id = r['la_id']
            if la_id not in leads:
                leads[la_id] = {
                    "la_id":             la_id,
                    "nom":               r['nom'],
                    "ville":             r['ville'],
                    "category":          r['category'],
                    "email":             r['email'],
                    "date_email_initial": r['date_email_initial'],
                    "relance_1":         None,
                    "relance_2":         None,
                    "relance_special":   None,
                }
            step = r['email_type']
            if step in ('relance_1', 'relance_2', 'relance_special'):
                leads[la_id][step] = {
                    "seq_id":          r['seq_id'],
                    "statut":          r['seq_statut'],
                    "date_planifiee":  r['date_planifiee'],
                    "date_envoi":      r['seq_date_envoi'],
                }

        return jsonify({
            "sequences": list(leads.values()),
            "total":     len(leads),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Nouvelles routes pour la page Relances ─────────────────────────────────

@emails_bp.route("/api/sequences/pending")
def api_sequences_pending():
    """Retourne toutes les séquences en pending_approval avec contenu."""
    try:
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT
                    seq.id, seq.lead_id, seq.email_type, seq.statut,
                    seq.date_planifiee, seq.email_objet, seq.email_corps,
                    lb.nom, lb.ville,
                    ee_init.email_destinataire AS email
                FROM email_sequences seq
                JOIN leads_audites la ON la.id = seq.lead_id
                JOIN leads_bruts lb   ON lb.id = la.lead_id
                JOIN emails_envoyes ee_init ON ee_init.id = seq.email_record_id
                WHERE seq.statut = 'pending_approval'
                ORDER BY seq.date_planifiee ASC
            """).fetchall()
        return jsonify({"sequences": [dict(r) for r in rows], "total": len(rows)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@emails_bp.route("/api/sequences/history")
def api_sequences_history():
    """Historique paginé des séquences avec stats globales."""
    try:
        statut = request.args.get("statut")
        page   = int(request.args.get("page", 1))
        limit  = int(request.args.get("limit", 30))
        offset = (page - 1) * limit

        where = ""
        params = []
        if statut:
            where = "WHERE seq.statut = ?"
            params.append(statut)

        with get_conn() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM email_sequences seq {where}", params
            ).fetchone()[0]

            rows = conn.execute(f"""
                SELECT
                    seq.id, seq.lead_id, seq.email_type, seq.statut,
                    seq.date_planifiee, seq.date_envoi,
                    lb.nom, lb.ville,
                    ee_init.email_destinataire AS email,
                    ee_init.date_envoi AS date_email_initial
                FROM email_sequences seq
                JOIN leads_audites la ON la.id = seq.lead_id
                JOIN leads_bruts lb   ON lb.id = la.lead_id
                JOIN emails_envoyes ee_init ON ee_init.id = seq.email_record_id
                {where}
                ORDER BY seq.date_planifiee DESC
                LIMIT ? OFFSET ?
            """, params + [limit, offset]).fetchall()

            # Stats globales
            stats_row = conn.execute("""
                SELECT
                    SUM(CASE WHEN statut='sent' THEN 1 ELSE 0 END)             AS sent,
                    SUM(CASE WHEN statut='sent' AND email_type='relance_1' THEN 1 ELSE 0 END) AS relance_1,
                    SUM(CASE WHEN statut='sent' AND email_type='relance_2' THEN 1 ELSE 0 END) AS relance_2,
                    SUM(CASE WHEN statut='sent' AND email_type='relance_special' THEN 1 ELSE 0 END) AS relance_special,
                    SUM(CASE WHEN statut='cancelled' THEN 1 ELSE 0 END)        AS cancelled,
                    SUM(CASE WHEN statut='pending_approval' THEN 1 ELSE 0 END) AS pending
                FROM email_sequences
            """).fetchone()

        return jsonify({
            "sequences":   [dict(r) for r in rows],
            "total":       total,
            "page":        page,
            "total_pages": max(1, (total + limit - 1) // limit),
            "stats":       dict(stats_row) if stats_row else {},
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@emails_bp.route("/api/sequences/approve", methods=["POST"])
def api_sequence_approve():
    """Approuve et envoie une séquence individuelle."""
    data   = request.get_json() or {}
    seq_id = data.get("seq_id")
    if not seq_id:
        return jsonify({"error": "seq_id requis"}), 400
    try:
        from services.email_sequence_service import EmailSequenceService
        ok = EmailSequenceService().approve_and_send(int(seq_id))
        return jsonify({"success": ok})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@emails_bp.route("/api/sequences/approve-bulk", methods=["POST"])
def api_sequences_approve_bulk():
    """Approuve et envoie plusieurs séquences (ou toutes si seq_ids=null)."""
    data    = request.get_json() or {}
    seq_ids = data.get("seq_ids")  # None = toutes
    try:
        from services.email_sequence_service import EmailSequenceService
        svc = EmailSequenceService()
        if seq_ids is None:
            # Toutes les pending_approval
            sent = svc.approve_all_pending()
        else:
            sent = 0
            for sid in seq_ids:
                if svc.approve_and_send(int(sid)):
                    sent += 1
        return jsonify({"success": True, "sent": sent})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@emails_bp.route("/api/sequences/cancel", methods=["POST"])
def api_sequence_cancel():
    """Annule une séquence planifiée ou en attente."""
    data   = request.get_json() or {}
    seq_id = data.get("seq_id")
    if not seq_id:
        return jsonify({"error": "seq_id requis"}), 400
    try:
        with get_conn() as conn:
            conn.execute(
                "UPDATE email_sequences SET statut='cancelled' WHERE id=? AND statut IN ('planned','pending_approval')",
                (int(seq_id),)
            )
            conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
