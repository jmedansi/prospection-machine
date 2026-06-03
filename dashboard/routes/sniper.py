# -*- coding: utf-8 -*-
"""
dashboard/routes/sniper.py — Routes API Sniper B2B

Endpoints :
  GET  /api/sniper/leads          — liste paginée des leads Sniper
  GET  /api/sniper/stats          — statistiques globales Sniper
  GET  /api/sniper/status         — état pipeline principal
  GET  /api/sniper/ecom-status    — état EcomScraper
  GET  /api/sniper/jobs-status    — état JobsScraper
  POST /api/sniper/launch         — lancer pipeline Ads
  POST /api/sniper/ecom-scan      — lancer EcomScraper
  POST /api/sniper/jobs-scan      — lancer JobsScraper
  POST /api/sniper/bodacc-scan    — lancer BODACC scanner
  POST /api/sniper/generate-emails — générer emails pour leads sans email
  POST /api/sniper/send-step1     — envoyer step 1 dans la limite du quota
  POST /api/sniper/send-step2     — envoyer step 2 (rapport) pour un lead
  POST /api/sniper/poll-imap      — vérifier réponses IMAP
  GET  /api/sniper/quota          — quota quotidien
  POST /api/sniper/set-quota      — modifier quota quotidien
"""

import logging
from flask import Blueprint, jsonify, request
from database.connection import get_conn

logger = logging.getLogger(__name__)
sniper_bp = Blueprint("sniper", __name__)


# ─── Leads ────────────────────────────────────────────────────────────────────

@sniper_bp.route("/api/sniper/leads")
def api_sniper_leads():
    try:
        source  = request.args.get("source", "")
        statut  = request.args.get("statut_prospection", "")
        tag     = request.args.get("tag_urgence", "")
        contact = request.args.get("contact", "")   # "avec"|"sans"|"catchall"
        limit   = int(request.args.get("limit", 200))
        page    = int(request.args.get("page", 1))
        offset  = (page - 1) * limit

        where, params = [], []
        source_list = ['ads', 'fb_ads', 'transparency', 'tech', 'jobs', 'bodacc']
        
        if source:
            where.append("lb.source LIKE ?")
            params.append(f"%{source}%")
        else:
            # Par défaut, on veut les sources Sniper
            source_clauses = [f"lb.source LIKE '%{s}%'" for s in source_list]
            where.append(f"({' OR '.join(source_clauses)})")
        if statut:
            where.append("la.statut_prospection = ?"); params.append(statut)
        if tag:
            where.append("lb.tag_urgence = ?"); params.append(tag)
        if contact == "avec":
            where.append("la.email_valide IS NOT NULL AND la.email_valide != '' AND la.is_catch_all != 1")
        elif contact == "sans":
            where.append("(la.email_valide IS NULL OR la.email_valide = '')")
        elif contact == "catchall":
            where.append("la.is_catch_all = 1")

        w = "WHERE " + " AND ".join(where)

        with get_conn() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM leads_bruts lb LEFT JOIN leads_audites la ON la.lead_id=lb.id {w}",
                params
            ).fetchone()[0]

            rows = conn.execute(f"""
                SELECT
                    lb.id, lb.nom, lb.site_web, lb.source, lb.tag_urgence, lb.statut,
                    la.id           AS audit_id,
                    la.email_valide,
                    la.ceo_prenom, la.ceo_nom,
                    la.mobile_score, la.desktop_score, la.score_seo,
                    la.statut_prospection,
                    la.lien_rapport,
                    la.score_urgence,
                    la.approuve
                FROM leads_bruts lb
                LEFT JOIN leads_audites la ON la.lead_id = lb.id
                {w}
                ORDER BY lb.date_scraping DESC
                LIMIT ? OFFSET ?
            """, params + [limit, offset]).fetchall()

        leads = [dict(r) for r in rows]
        return jsonify({"leads": leads, "total": total, "page": page})
    except Exception as e:
        logger.error(f"api_sniper_leads: {e}")
        return jsonify({"error": str(e)}), 500


# ─── Lead detail ──────────────────────────────────────────────────────────────

@sniper_bp.route("/api/sniper/lead/<int:lead_id>")
def api_sniper_lead_detail(lead_id):
    try:
        with get_conn() as conn:
            row = conn.execute("""
                SELECT
                    lb.*,
                    la.id            AS audit_id,
                    la.mobile_score, la.desktop_score,
                    la.score_urgence, la.score_performance, la.score_seo,
                    la.email_objet, la.email_corps,
                    la.approuve, la.lien_rapport, la.lien_pdf,
                    la.probleme_principal, la.service_suggere,
                    la.lcp_ms, la.cms_detected,
                    la.ceo_prenom, la.ceo_nom,
                    la.email_valide  AS email_valide_audit,
                    la.copywriting_mode, la.is_catch_all,
                    la.statut_prospection,
                    la.date_audit       AS date_generation
                FROM leads_bruts lb
                LEFT JOIN leads_audites la ON la.lead_id = lb.id
                WHERE lb.id = ?
            """, (lead_id,)).fetchone()
        if not row:
            return jsonify({"error": "Lead introuvable"}), 404
        return jsonify(dict(row))
    except Exception as e:
        logger.error(f"api_sniper_lead_detail({lead_id}): {e}")
        return jsonify({"error": str(e)}), 500


# ─── Stats ────────────────────────────────────────────────────────────────────

@sniper_bp.route("/api/sniper/stats")
def api_sniper_stats():
    try:
        from services.sniper_sender_service import get_sniper_daily_quota, get_sniper_quota_remaining

        with get_conn() as conn:
            _sniper_sources = "('ads','fb_ads','transparency','ecom','tech','jobs','bodacc')"

            sources = dict(conn.execute(f"""
                SELECT source, COUNT(*) FROM leads_bruts
                WHERE source IN {_sniper_sources}
                GROUP BY source
            """).fetchall())

            total_leads = conn.execute(
                f"SELECT COUNT(*) FROM leads_bruts WHERE source IN {_sniper_sources}"
            ).fetchone()[0]

            emails_generes = conn.execute(f"""
                SELECT COUNT(*) FROM leads_audites la
                JOIN leads_bruts lb ON lb.id = la.lead_id
                WHERE lb.source IN {_sniper_sources}
                  AND la.email_corps IS NOT NULL AND la.email_corps != ''
            """).fetchone()[0]

            step1_envoyes = conn.execute(f"""
                SELECT COUNT(*) FROM leads_audites la
                JOIN leads_bruts lb ON lb.id = la.lead_id
                WHERE lb.source IN {_sniper_sources}
                  AND la.statut_prospection = 'step1_envoye'
            """).fetchone()[0]

            reponses = conn.execute(f"""
                SELECT COUNT(*) FROM leads_audites la
                JOIN leads_bruts lb ON lb.id = la.lead_id
                WHERE lb.source IN {_sniper_sources}
                  AND la.statut_prospection = 'repondu'
            """).fetchone()[0]

            step2_livres = conn.execute(f"""
                SELECT COUNT(*) FROM leads_audites la
                JOIN leads_bruts lb ON lb.id = la.lead_id
                WHERE lb.source IN {_sniper_sources}
                  AND la.statut_prospection = 'lien_envoye'
            """).fetchone()[0]

        daily_quota    = get_sniper_daily_quota()
        quota_remaining = get_sniper_quota_remaining()

        return jsonify({
            "total_leads":      total_leads,
            "emails_generes":   emails_generes,
            "step1_envoyes":    step1_envoyes,
            "reponses":         reponses,
            "step2_livres":     step2_livres,
            "daily_quota":      daily_quota,
            "quota_remaining":  quota_remaining,
            "by_source":        sources,
        })
    except Exception as e:
        logger.error(f"api_sniper_stats: {e}")
        return jsonify({"error": str(e)}), 500


# ─── Status pipelines ─────────────────────────────────────────────────────────

@sniper_bp.route("/api/sniper/status")
def api_sniper_status():
    try:
        from services.sniper_runner import get_sniper_status
        state = get_sniper_status()
        logs  = state.pop("logs", [])
        return jsonify({**state, "logs": logs[-50:] if logs else []})
    except Exception as e:
        return jsonify({"running": False, "logs": [], "error": str(e)})


@sniper_bp.route("/api/sniper/ecom-status")
@sniper_bp.route("/api/sniper/tech-status")   # alias legacy
def api_sniper_ecom_status():
    try:
        from services.sniper_runner import get_ecom_status
        return jsonify(get_ecom_status())
    except Exception as e:
        return jsonify({"running": False, "error": str(e)})


@sniper_bp.route("/api/sniper/jobs-status")
def api_sniper_jobs_status():
    try:
        from services.sniper_runner import get_jobs_status
        return jsonify(get_jobs_status())
    except Exception as e:
        return jsonify({"running": False, "error": str(e)})


# ─── Lancers ──────────────────────────────────────────────────────────────────

@sniper_bp.route("/api/sniper/launch", methods=["POST"])
def api_sniper_launch():
    try:
        data         = request.get_json() or {}
        keywords     = data.get("keywords", [])
        country      = data.get("country", "fr")
        city         = data.get("city", "").strip()
        max_per_kw   = int(data.get("max_per_kw", 30))
        pages_per_kw = int(data.get("pages_per_kw", 5))
        min_leads    = int(data.get("min_leads", 0))
        if not keywords:
            return jsonify({"error": "keywords requis"}), 400

        # Ville manuelle intégrée dans les mots-clés si fournie
        # La rotation auto prend le relais (sans réappliquer la ville fixe) si min_leads > 0
        if city and not min_leads:
            # Ville fixe seulement — on l'injecte dans les mots-clés
            keywords = [f"{kw} {city}" if city.lower() not in kw.lower() else kw for kw in keywords]

        from services.sniper_runner import launch_sniper
        ok, msg = launch_sniper(
            keywords=keywords,
            country=country,
            city=city if min_leads else "",   # transmis au pipeline pour la 1ère passe
            max_per_kw=max_per_kw,
            pages_per_kw=pages_per_kw,
            min_leads=min_leads,
        )
        if not ok:
            return jsonify({"error": msg}), 409
        return jsonify({"ok": True, "message": msg})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@sniper_bp.route("/api/sniper/ecom-scan", methods=["POST"])
@sniper_bp.route("/api/sniper/tech-scan", methods=["POST"])   # alias legacy
def api_sniper_ecom_scan():
    try:
        data      = request.get_json() or {}
        keywords  = data.get("keywords")
        city      = data.get("city", "").strip()
        max_leads = int(data.get("max_leads", 50))
        min_leads = int(data.get("min_leads", 0))

        if keywords and city:
            keywords = [f"{kw} {city}" if city.lower() not in kw.lower() else kw for kw in keywords]

        from services.sniper_runner import launch_ecom_scraper
        ok, msg = launch_ecom_scraper(keywords=keywords, max_leads=max_leads, min_leads=min_leads)
        if not ok:
            return jsonify({"error": msg}), 409
        return jsonify({"ok": True, "message": msg})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@sniper_bp.route("/api/sniper/jobs-scan", methods=["POST"])
def api_sniper_jobs_scan():
    try:
        data      = request.get_json() or {}
        keywords  = data.get("keywords")
        city      = data.get("city", "").strip()
        max_leads = int(data.get("max_leads", 50))
        days_back = int(data.get("days_back", 7))
        
        if keywords and city:
            keywords = [f"{kw} {city}" if city.lower() not in kw.lower() else kw for kw in keywords]
            
        from services.sniper_runner import launch_jobs_scraper
        ok, msg = launch_jobs_scraper(keywords=keywords, max_leads=max_leads, days_back=days_back)
        if not ok:
            return jsonify({"error": msg}), 409
        return jsonify({"ok": True, "message": msg})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@sniper_bp.route("/api/sniper/bodacc-scan", methods=["POST"])
def api_sniper_bodacc_scan():
    try:
        data = request.get_json() or {}
        from services.sniper_runner import launch_bodacc_scanner
        ok, msg = launch_bodacc_scanner()
        if not ok:
            return jsonify({"error": msg}), 409
        return jsonify({"ok": True, "message": msg})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Arrêt d'urgence des scrapers ─────────────────────────────────────────────









@sniper_bp.route("/api/sniper/bodacc-stop", methods=["POST"])
def api_sniper_bodacc_stop():
    """Arrête le BODACC scanner en cours."""
    try:
        from services.sniper_runner import stop_bodacc_scanner
        stop_bodacc_scanner()
        return jsonify({"ok": True, "message": "Arrêt demandé pour le BODACC scanner"})
    except Exception as e:
        logger.error(f"api_sniper_bodacc_stop: {e}")
        return jsonify({"error": str(e)}), 500


@sniper_bp.route("/api/sniper/bodacc-scan", methods=["POST"])
def api_sniper_bodacc_scan_old():
    try:
        data = request.get_json() or {}
        date = data.get("date")
        from sniper.bodacc_scanner import BodaccScanner
        result = BodaccScanner().scan(date=date)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Emails ───────────────────────────────────────────────────────────────────

@sniper_bp.route("/api/sniper/generate-emails", methods=["POST"])
def api_sniper_generate_emails():
    try:
        from services.task_worker import enqueue_task, task_generate_emails
        campaign_id = request.get_json().get("campaign_id") if request.is_json else None
        task_id = enqueue_task(task_generate_emails, kwargs={"campaign_id": campaign_id}, label="Génération d'emails Sniper")
        return jsonify({"ok": True, "task_id": task_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@sniper_bp.route("/api/tasks/status/<task_id>")
def api_task_status(task_id):
    try:
        from services.task_worker import get_task_status
        status = get_task_status(task_id)
        if not status:
            return jsonify({"error": "Tâche introuvable"}), 404
        return jsonify(status)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@sniper_bp.route("/api/sniper/send-step1", methods=["POST"])
def api_sniper_send_step1():
    try:
        from services.sniper_sender_service import send_sniper_step1_async
        ok, msg = send_sniper_step1_async()
        if not ok:
            return jsonify({"error": msg}), 409
        return jsonify({"ok": True, "message": msg})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@sniper_bp.route("/api/sniper/send-step2", methods=["POST"])
def api_sniper_send_step2():
    try:
        data     = request.get_json() or {}
        audit_id = data.get("audit_id")
        if not audit_id:
            return jsonify({"error": "audit_id requis"}), 400
        from sniper.rapport_generator import send_step2_report
        result = send_step2_report(audit_id=audit_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@sniper_bp.route("/api/sniper/poll-imap", methods=["POST"])
def api_sniper_poll_imap():
    try:
        data  = request.get_json() or {}
        hours = int(data.get("hours", 48))
        from sniper.imap_poller import ImapPoller
        result = ImapPoller().poll(hours_back=hours)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── FB Ads ───────────────────────────────────────────────────────────────────

@sniper_bp.route("/api/sniper/fb-ads-scan", methods=["POST"])
def api_sniper_fb_ads_scan():
    try:
        data         = request.get_json() or {}
        search_terms = data.get("search_terms", [])
        city         = data.get("city", "").strip()
        country      = data.get("country", "FR").upper()
        max_pages    = int(data.get("max_pages", 5))
        min_leads    = int(data.get("min_leads", 0))
        if not search_terms:
            return jsonify({"error": "search_terms requis"}), 400

        if city:
            search_terms = [f"{kw} {city}" if city.lower() not in kw.lower() else kw for kw in search_terms]

        from services.sniper_runner import launch_fb_ads_scraper
        ok, msg = launch_fb_ads_scraper(
            search_terms=search_terms,
            country=country,
            max_pages=max_pages,
            min_leads=min_leads,
        )
        if not ok:
            return jsonify({"error": msg}), 409
        return jsonify({"ok": True, "message": msg})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@sniper_bp.route("/api/sniper/fb-ads-status")
def api_sniper_fb_ads_status():
    try:
        from services.sniper_runner import get_fb_ads_status
        return jsonify(get_fb_ads_status())
    except Exception as e:
        return jsonify({"running": False, "error": str(e)})


# ─── Source 6 : Google Ads Transparency Center ───────────────────────────────

@sniper_bp.route("/api/sniper/transparency-scan", methods=["POST"])
def api_sniper_transparency_scan():
    try:
        data         = request.get_json(force=True) or {}
        keywords     = data.get("keywords", [])
        country      = data.get("country", "FR").upper()
        max_per_kw   = int(data.get("max_per_kw", 20))
        parallel     = int(data.get("parallel", 3))
        campaign_name = data.get("campaign_name")

        if not keywords:
            return jsonify({"error": "keywords requis"}), 400

        from services.sniper_runner import launch_transparency_scraper
        ok, msg = launch_transparency_scraper(
            keywords=keywords,
            country=country,
            max_per_kw=max_per_kw,
            parallel_enrich=parallel,
            campaign_name=campaign_name,
        )
        if ok:
            return jsonify({"status": "launched", "keywords": keywords})
        return jsonify({"error": msg}), 409
    except Exception as e:
        logger.error(f"api_sniper_transparency_scan: {e}")
        return jsonify({"error": str(e)}), 500


@sniper_bp.route("/api/sniper/transparency-status")
def api_sniper_transparency_status():
    try:
        from services.sniper_runner import get_transparency_status
        return jsonify(get_transparency_status())
    except Exception as e:
        return jsonify({"running": False, "error": str(e)})


# ─── Quota ────────────────────────────────────────────────────────────────────

@sniper_bp.route("/api/sniper/daily-batch")
def api_sniper_daily_batch():
    try:
        from scraper.sniper.keyword_bank import get_daily_batch, ALL_KEYWORDS
        n = int(request.args.get("n", 10))
        return jsonify({
            "keywords": get_daily_batch(n=n),
            "total_bank": len(ALL_KEYWORDS),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@sniper_bp.route("/api/sniper/settings", methods=["GET", "POST"])
def api_sniper_settings():
    try:
        with get_conn() as conn:
            if request.method == "POST":
                data = request.get_json(force=True) or {}
                for key, value in data.items():
                    if key.startswith("sniper_"):
                        conn.execute(
                            "INSERT OR REPLACE INTO planning_settings (key, value) VALUES (?, ?)",
                            (key, str(value))
                        )
                conn.commit()
                return jsonify({"ok": True})
            else:
                rows = conn.execute(
                    "SELECT key, value FROM planning_settings WHERE key LIKE 'sniper%'"
                ).fetchall()
                return jsonify({r["key"]: r["value"] for r in rows})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@sniper_bp.route("/api/sniper/quota")
def api_sniper_quota():
    try:
        from services.sniper_sender_service import get_sniper_daily_quota, get_sniper_quota_remaining
        return jsonify({
            "daily_quota":     get_sniper_daily_quota(),
            "quota_remaining": get_sniper_quota_remaining(),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@sniper_bp.route("/api/sniper/set-quota", methods=["POST"])
def api_sniper_set_quota():
    try:
        data  = request.get_json() or {}
        quota = int(data.get("daily_quota", 20))
        with get_conn() as conn:
            conn.execute("""
                INSERT INTO planning_settings (key, value) VALUES ('sniper_daily_quota', ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """, (str(quota),))
            conn.commit()
        return jsonify({"ok": True, "daily_quota": quota})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Routes STOP — arrêt gracieux de chaque pipeline ────────────────────────

@sniper_bp.route("/api/sniper/stop", methods=["POST"])
def api_sniper_stop():
    """Arrêt gracieux du pipeline Google Ads (laisse l'enrichissement finir)."""
    try:
        from services.sniper_runner import stop_sniper
        stop_sniper()
        return jsonify({"ok": True, "message": "Arrêt demandé — le pipeline finira les leads en cours"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@sniper_bp.route("/api/sniper/force-stop", methods=["POST"])
def api_sniper_force_stop():
    """Arrêt brutal du pipeline Sniper (ferme le navigateur)."""
    try:
        from services.sniper_runner import force_stop_sniper
        force_stop_sniper()
        return jsonify({"ok": True, "message": "Arrêt brutal effectué (navigateur fermé)"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@sniper_bp.route("/api/sniper/fb-ads-stop", methods=["POST"])
def api_sniper_fb_ads_stop():
    """Arrêt gracieux du pipeline Facebook Ads."""
    try:
        from services.sniper_runner import stop_fb_ads_scraper
        stop_fb_ads_scraper()
        return jsonify({"ok": True, "message": "Arrêt FB Ads demandé"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@sniper_bp.route("/api/sniper/ecom-stop", methods=["POST"])
def api_sniper_ecom_stop():
    """Arrêt gracieux du pipeline E-com/Tech."""
    try:
        from services.sniper_runner import stop_ecom_scraper
        stop_ecom_scraper()
        return jsonify({"ok": True, "message": "Arrêt E-com demandé"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@sniper_bp.route("/api/sniper/jobs-stop", methods=["POST"])
def api_sniper_jobs_stop():
    """Arrêt gracieux du pipeline Jobs."""
    try:
        from services.sniper_runner import stop_jobs_scraper
        stop_jobs_scraper()
        return jsonify({"ok": True, "message": "Arrêt Jobs demandé"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
