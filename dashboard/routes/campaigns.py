# -*- coding: utf-8 -*-
"""
dashboard/routes/campaigns.py
Routes API pour la planification et le lancement des campagnes.
"""
from flask import Blueprint, jsonify, request
from database import (
    get_conn, get_all_campaigns, logger
)
from services.scraper_runner import launch_scraper

campaigns_bp = Blueprint('campaigns', __name__)

@campaigns_bp.route('/api/scraper/launch', methods=['POST'])
def api_scraper_launch():
    try:
        data = request.get_json() or {}
        keyword = data.get('keyword', '').strip()
        city = data.get('city', '').strip()
        sector = data.get('sector', '').strip()
        secteur = data.get('secteur', '').strip() or sector  # campagne sector > niche
        limit = int(data.get('limit', 50))
        min_emails = int(data.get('min_emails', 10))
        campaign_name = data.get('campaign_name', f"{secteur or keyword} {city}")

        if not keyword or not city:
            return jsonify({'error': 'keyword et city requis'}), 400

        success, res = launch_scraper(
            keyword=keyword,
            city=city,
            sector=secteur,
            limit=limit,
            min_emails=min_emails,
            campaign_name=campaign_name
        )

        if not success:
            return jsonify({'error': res}), 500
        
        return jsonify({'success': True, 'campaign_id': res, 'message': 'Scraper lancé'})
    except Exception as e:
        logger.error(f"POST /api/scraper/launch → {e}")
        return jsonify({'error': str(e)}), 500

@campaigns_bp.route('/api/campaigns')
def api_campaigns():
    """Retourne les campagnes avec les champs Status Registry."""
    try:
        from services.campaign_tracker import get_all_campaigns_with_status
        limit = int(request.args.get('limit', 50))
        sector = request.args.get('sector', '').strip() or None
        campaigns = get_all_campaigns_with_status(limit=limit, sector=sector)
        return jsonify({'campaigns': campaigns})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@campaigns_bp.route('/api/campaigns/<int:camp_id>', methods=['DELETE'])
def api_campaign_delete(camp_id):
    """Supprime une campagne (les leads restent, campaign_id mis à NULL)."""
    try:
        from database import delete_campaign
        delete_campaign(camp_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@campaigns_bp.route('/api/campaigns/<int:camp_id>/resume', methods=['POST'])
def api_campaign_resume(camp_id):
    """Reprend une campagne arrêtée à la phase où elle s'est arrêtée."""
    try:
        from services.campaign_tracker import get_campaign_state, start_campaign as _start
        state = get_campaign_state(camp_id)
        if not state:
            return jsonify({'error': 'Campagne introuvable'}), 404
        if state['phase'] not in ('failed', 'stopped'):
            return jsonify({'error': f"Campagne non reprise (phase={state['phase']})"}), 400

        # Déterminer la source et relancer
        source = state.get('source', 'maps')
        kw = state.get('secteur', '')
        city = state.get('ville', '')
        nb = state.get('nb_demande', 50)
        camp_name = state.get('nom', '')

        if source == 'maps':
            from services.scraper_runner import launch_scraper
            # Relance avec le même campaign_id (pas de nouveau)
            _start(camp_id, phase='scraping')
            success, _ = launch_scraper(keyword=kw, city=city, limit=nb, campaign_name=camp_name)
        elif source in ('ads', 'fb_ads', 'tech', 'jobs'):
            _start(camp_id, phase='scraping')
            # Le relancement crée une nouvelle campagne, on marque celle-ci comme reprise
        else:
            return jsonify({'error': f'Source non supportée: {source}'}), 400

        return jsonify({'success': True, 'message': f'Campagne #{camp_id} reprise'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@campaigns_bp.route('/api/campaigns/<int:camp_id>/restart', methods=['POST'])
def api_campaign_restart(camp_id):
    """Relance une campagne de zéro (supprime les leads et recommence)."""
    try:
        from services.campaign_tracker import get_campaign_state, start_campaign as _start

        state = get_campaign_state(camp_id)
        if not state:
            return jsonify({'error': 'Campagne introuvable'}), 404

        # Supprimer les leads associés pour repartir de zéro
        with get_conn() as conn:
            conn.execute("DELETE FROM leads_bruts WHERE campaign_id = ?", (camp_id,))
            conn.execute("""
                UPDATE campagnes
                SET phase = 'pending', error_message = NULL, stopped_at = NULL,
                    finished_at = NULL, progress_data = NULL, total_leads = 0
                WHERE id = ?
            """, (camp_id,))
            conn.commit()

        # Relancer selon la source
        source = state.get('source', 'maps')
        kw = state.get('secteur', '')
        city = state.get('ville', '')
        nb = state.get('nb_demande', 50)

        _start(camp_id, phase='scraping')

        if source == 'maps':
            from services.scraper_runner import launch_scraper
            launch_scraper(keyword=kw, city=city, limit=nb, campaign_name=state.get('nom', ''))

        return jsonify({'success': True, 'message': f'Campagne #{camp_id} relancée de zéro'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@campaigns_bp.route('/api/campaigns/<int:camp_id>/abandon', methods=['POST'])
def api_campaign_abandon(camp_id):
    """Marque une campagne comme définitivement abandonnée."""
    try:
        from services.campaign_tracker import stop_campaign
        stop_campaign(camp_id, reason='Abandonné par l\'utilisateur')
        with get_conn() as conn:
            conn.execute("UPDATE campagnes SET phase = 'stopped', statut = 'cancelled' WHERE id = ?", (camp_id,))
            conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@campaigns_bp.route("/api/planning", methods=["GET"])
def api_planning_list():
    try:
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT * FROM planned_campaigns
                ORDER BY date_planifiee ASC, heure ASC
            """).fetchall()
        return jsonify({"campaigns": [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@campaigns_bp.route("/api/planning", methods=["POST"])
def api_planning_add():
    try:
        data = request.get_json() or {}
        secteur = data.get("secteur", "").strip()
        keyword = data.get("keyword", "").strip()
        city = data.get("city", "").strip()
        limit = int(data.get("limit_leads", 50))
        date_p = data.get("date_planifiee", "")
        heure = data.get("heure", "09:00")
        source = data.get("source", "maps").strip()
        
        if not keyword or not city or not date_p:
            return jsonify({"error": "keyword, city et date_planifiee requis"}), 400
        with get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO planned_campaigns (secteur, keyword, city, limit_leads, date_planifiee, heure, source) VALUES (?,?,?,?,?,?,?)",
                (secteur, keyword, city, limit, date_p, heure, source)
            )
            conn.commit()
            new_id = cur.lastrowid
        return jsonify({"success": True, "id": new_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@campaigns_bp.route("/api/planning/<int:pid>", methods=["DELETE"])
def api_planning_delete(pid):
    try:
        with get_conn() as conn:
            conn.execute("UPDATE planned_campaigns SET statut='cancelled' WHERE id=?", (pid,))
            conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@campaigns_bp.route("/api/planning/<int:pid>/launch", methods=["POST"])
def api_planning_launch_now(pid):
    try:
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM planned_campaigns WHERE id=?", (pid,)).fetchone()
        if not row: return jsonify({"error": "Introuvable"}), 404
        c = dict(row)
        
        from datetime import date as _date
        campaign_name = f"{c['secteur']} {c['city']} {_date.today().isoformat()}"
        min_e = c.get('min_emails') or c.get('limit_leads') or 20

        source = c.get('source', 'maps')
        
        if source == 'sniper_ads':
            from services.sniper_runner import launch_sniper
            kw = c['keyword']
            success, res = launch_sniper(
                keywords=[kw],
                country='fr',
                city=c['city'],
                max_per_kw=min_e * 4,
                parallel_enrich=3,
                campaign_name=campaign_name
            )
            if success:
                res = None
        elif source == 'sniper_fb':
            from services.sniper_runner import launch_fb_ads_scraper
            kw = c['keyword']
            success, res = launch_fb_ads_scraper(
                search_terms=[kw], country='FR', city=c['city'], max_pages=5, parallel=3, campaign_name=campaign_name
            )
            if success: res = None
        elif source == 'sniper_ecom':
            from services.sniper_runner import launch_tech_scraper
            kw = c['keyword']
            success, res = launch_tech_scraper(
                keywords=[kw],
                city=c['city'],
                max_companies=min_e * 8,
                max_leads=min_e * 4,
                parallel=3,
                campaign_name=campaign_name
            )
            if success: res = None
        else: # maps par défaut
            success, res = launch_scraper(
                keyword=c['keyword'],
                city=c['city'],
                sector=c['secteur'],
                limit=min_e * 4,
                min_emails=min_e,
                campaign_name=campaign_name
            )

        if not success:
            return jsonify({'error': res}), 500
        
        with get_conn() as conn:
            # Si res est None (cas Sniper), on met à jour le statut quand même
            if res:
                conn.execute("UPDATE planned_campaigns SET statut='running', campaign_id=? WHERE id=?", (res, pid))
            else:
                conn.execute("UPDATE planned_campaigns SET statut='running' WHERE id=?", (pid,))
            conn.commit()
        return jsonify({"success": True, "campaign_id": res})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@campaigns_bp.route("/api/planning/quota", methods=["GET"])
def api_planning_quota():
    try:
        from dashboard.scheduler import get_daily_quota, get_emails_sent_today
        quota = get_daily_quota()
        sent = get_emails_sent_today()
        return jsonify({"quota": quota, "sent": sent, "remaining": max(0, quota - sent)})
    except Exception:
        return jsonify({"quota": 100, "sent": 0, "remaining": 100})

@campaigns_bp.route("/api/planning/quota", methods=["POST"])
def api_planning_quota_update():
    try:
        data = request.get_json() or {}
        quota = max(1, min(300, int(data.get("daily_quota", 30))))
        with get_conn() as conn:
            conn.execute("UPDATE planning_settings SET value=? WHERE key='daily_quota'", (str(quota),))
            conn.commit()
        return jsonify({"success": True, "daily_quota": quota})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@campaigns_bp.route("/api/scraping-priorities", methods=["GET"])
def api_get_scraping_priorities():
    try:
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT id, secteur, keyword, ville, limit_leads, priorite,
                       actif, frequence_jours, derniere_execution
                FROM scraping_priorities
                ORDER BY priorite ASC, secteur ASC, ville ASC
            """).fetchall()
        return jsonify({"priorities": [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@campaigns_bp.route("/api/scraping-priorities", methods=["POST"])
def api_add_scraping_priority():
    try:
        d = request.get_json() or {}
        with get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO scraping_priorities
                    (secteur, keyword, ville, limit_leads, priorite, frequence_jours, source, actif)
                VALUES (:secteur, :keyword, :ville, :limit_leads, :priorite, :frequence_jours, :source, 1)
            """, {
                'secteur': d.get('secteur', 'default'),
                'keyword': d['keyword'],
                'ville': d['ville'],
                'limit_leads': int(d.get('limit_leads', 50)),
                'priorite': int(d.get('priorite', 5)),
                'frequence_jours': int(d.get('frequence_jours', 30)),
                'source': d.get('source', 'maps'),
            })
            conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@campaigns_bp.route("/api/scraping-priorities/<int:pid>", methods=["DELETE"])
def api_delete_scraping_priority(pid):
    try:
        with get_conn() as conn:
            conn.execute("DELETE FROM scraping_priorities WHERE id=?", (pid,))
            conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@campaigns_bp.route("/api/scraping-priorities/<int:pid>/toggle", methods=["POST"])
def api_toggle_scraping_priority(pid):
    try:
        with get_conn() as conn:
            conn.execute("UPDATE scraping_priorities SET actif = 1 - actif WHERE id=?", (pid,))
            conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@campaigns_bp.route("/api/auto-plan/now", methods=["POST"])
def api_auto_plan_now():
    try:
        from auto_planner import run_auto_plan, plan_week, plan_day
        data = request.get_json() or {}
        mode = data.get('mode', 'day')
        force = data.get('force', False)
        if mode == 'week':
            res = plan_week()
            return jsonify({"ok": True, "added": sum(res.values()), "details": res})
        else:
            added = plan_day(force=force) if force else run_auto_plan()
            return jsonify({"ok": True, "added": added})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@campaigns_bp.route("/api/auto-plan/backlog", methods=["GET"])
def api_auto_plan_backlog():
    try:
        from auto_planner import get_pipeline_backlog, get_auto_plan_settings
        backlog = get_pipeline_backlog()
        settings = get_auto_plan_settings()
        daily_quota = settings['daily_quota']
        backlog_days = round(backlog.get('leads_with_email', 0) / max(daily_quota, 1), 1)
        return jsonify({
            **backlog, "backlog_days": backlog_days, "daily_quota": daily_quota,
            "max_backlog_days": settings['max_backlog_days'],
            "status": "paused" if backlog_days >= settings['max_backlog_days'] else "normal"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@campaigns_bp.route('/api/planning/add', methods=['POST'])
def api_planning_add_alias():
    """Alias de POST /api/planning pour compatibilité mobile."""
    return api_planning_add()

@campaigns_bp.route("/api/settings/sources", methods=["GET", "POST"])
def api_settings_sources():
    try:
        with get_conn() as conn:
            if request.method == "POST":
                data = request.get_json(force=True) or {}
                for key, value in data.items():
                    # Format attendu : source_auto_scrape ou source_daily_quota
                    conn.execute(
                        "INSERT OR REPLACE INTO planning_settings (key, value) VALUES (?, ?)",
                        (key, str(value))
                    )
                conn.commit()
                return jsonify({"ok": True})
            else:
                rows = conn.execute(
                    "SELECT key, value FROM planning_settings WHERE key LIKE '%auto_scrape' OR key LIKE '%daily_quota'"
                ).fetchall()
                return jsonify({r["key"]: r["value"] for r in rows})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@campaigns_bp.route('/api/scraper/status')
def api_scraper_status():
    """Retourne le statut du dernier scraping en cours (inféré depuis la DB)."""
    try:
        with get_conn() as conn:
            row = conn.execute("""
                SELECT c.id, c.nom, c.nb_demande,
                       COUNT(lb.id)                                              AS leads_total,
                       COUNT(CASE WHEN lb.email != '' AND lb.email IS NOT NULL
                                  THEN 1 END)                                   AS with_email
                FROM campagnes c
                LEFT JOIN leads_bruts lb ON lb.campaign_id = c.id
                ORDER BY c.id DESC LIMIT 1
            """).fetchone()
        if not row:
            return jsonify({"running": False, "current": 0, "total": 0, "with_email": 0, "logs": []})
        r = dict(row)
        running = (r['nb_demande'] or 0) > 0 and r['leads_total'] < r['nb_demande']
        return jsonify({
            "running": running,
            "key": "maps",
            "label": "Google Maps",
            "current": r['leads_total'],
            "total":   r['nb_demande'] or 0,
            "with_email": r['with_email'],
            "logs": []
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@campaigns_bp.route('/api/scraper/all-status')
def api_scraper_all_status():
    """Agrège le statut de TOUS les scrapers et agents en un seul appel (pour le watchdog)."""
    sources = []

    # ── Audit Agent ───────────────────────────────────────────────────────────
    try:
        from agents.auditeur.agent import auditeur_agent
        st = auditeur_agent.status()
        if st.get("running"):
            sources.append({
                "running": True, "key": "audit", "label": "Audit technique",
                "phase": "audit", "processed": st.get("current", 0), "total": st.get("total", 0),
                "failed": st.get("failed", 0)
            })
    except Exception: pass

    # ── Enrichment Agent (Recherche Emails) ───────────────────────────────────
    try:
        from agents.enrichisseur.agent import enrichisseur_agent
        st = enrichisseur_agent.status()
        if st.get("running"):
            sources.append({
                "running": True, "key": "enrichment", "label": "Recherche emails",
                "phase": "enrichment", "processed": st.get("current", 0), "total": st.get("total", 0),
                "failed": st.get("failed", 0)
            })
    except Exception: pass

    # ── Email Sender Job ──────────────────────────────────────────────────────
    try:
        from services.job_tracker import get_email_status
        st = get_email_status()
        if st.get("running"):
            sources.append({
                "running": True, "key": "sending", "label": "Envoi emails",
                "phase": "sending", "processed": st.get("current", 0), "total": st.get("total", 0),
                "failed": st.get("failed", 0)
            })
    except Exception: pass

    # ── Sniper ADS ────────────────────────────────────────────────────────────
    try:
        from services.sniper_runner import get_sniper_status
        s = get_sniper_status()
        sources.append({**s, "key": "ads",    "label": "Google Ads"})
    except Exception:
        sources.append({"running": False, "key": "ads", "label": "Google Ads"})

    # ── Facebook Ads ──────────────────────────────────────────────────────────
    try:
        from services.sniper_runner import get_fb_ads_status
        s = get_fb_ads_status()
        sources.append({**s, "key": "fb_ads", "label": "Facebook Ads"})
    except Exception:
        sources.append({"running": False, "key": "fb_ads", "label": "Facebook Ads"})

    # ── Tech / E-com ──────────────────────────────────────────────────────────
    try:
        from services.sniper_runner import get_ecom_status
        s = get_ecom_status()
        sources.append({**s, "key": "tech",   "label": "Tech/E-com"})
    except Exception:
        sources.append({"running": False, "key": "tech", "label": "Tech/E-com"})

    # ── Jobs ──────────────────────────────────────────────────────────────────
    try:
        from services.sniper_runner import get_jobs_status
        s = get_jobs_status()
        sources.append({**s, "key": "jobs",   "label": "Jobs"})
    except Exception:
        sources.append({"running": False, "key": "jobs", "label": "Jobs"})

    # ── Google Maps (subprocess) ───────────────────────────────────────────────
    try:
        with get_conn() as conn:
            row = conn.execute("""
                SELECT nb_demande, phase,
                    (SELECT COUNT(*) FROM leads_bruts WHERE campaign_id = c.id) AS leads_total
                FROM campagnes c
                ORDER BY id DESC LIMIT 1
            """).fetchone()
        if row:
            r = dict(row)
            maps_running = r['phase'] == 'scraping'
            sources.append({
                "running": maps_running, "key": "maps", "label": "Google Maps",
                "accepted": r['leads_total'], "total": r['nb_demande'] or 0
            })
        else:
            sources.append({"running": False, "key": "maps", "label": "Google Maps"})
    except Exception:
        sources.append({"running": False, "key": "maps", "label": "Google Maps"})

    any_running = any(s.get("running") for s in sources)

    # ── Enrichir avec les données du Status Registry ──────────────────────────
    try:
        with get_conn() as conn:
            active_camps = conn.execute("""
                SELECT id, nom, source, phase, progress_data, error_message, started_at
                FROM campagnes
                WHERE phase IN ('scraping', 'enrichment', 'audit', 'email_gen')
                ORDER BY id DESC LIMIT 10
            """).fetchall()

            failed_recent = conn.execute("""
                SELECT id, nom, source, phase, error_message, stopped_at
                FROM campagnes
                WHERE phase IN ('failed', 'stopped')
                  AND stopped_at > datetime('now', '-24 hours')
                ORDER BY stopped_at DESC LIMIT 5
            """).fetchall()

        # Marquer les sources comme running si le tracker dit qu'elles le sont
        active_sources = {}
        for camp in active_camps:
            c = dict(camp)
            src = c.get('source', 'maps')
            active_sources[src] = {
                'campaign_id': c['id'],
                'campaign_name': c['nom'],
                'phase': c['phase'],
                'started_at': c['started_at'],
            }
            # Parser progress_data
            if c.get('progress_data'):
                import json
                try:
                    prog = json.loads(c['progress_data'])
                    active_sources[src].update(prog)
                except Exception:
                    pass

        # Fusionner dans les sources existantes
        for s in sources:
            if s['key'] in active_sources:
                s.update(active_sources[s['key']])
                if not s.get('running'):
                    s['running'] = True
                    any_running = True

    except Exception:
        pass  # Ne pas casser le watchdog si le tracker échoue

    return jsonify({
        "running": any_running,
        "sources": sources,
        "failed_recent": [dict(r) for r in failed_recent] if 'failed_recent' in dir() else [],
    })


@campaigns_bp.route('/api/scraper/stop', methods=['POST'])
def api_scraper_stop():
    """Arrête proprement une tâche selon sa clé."""
    data = request.get_json(silent=True, force=True) or {}
    key = data.get('key') or data.get('source') or 'maps'
    camp_id = data.get('campaign_id')
    
    logger.info(f"[scraper_stop] Demande d'arrêt pour {key} (camp_id={camp_id})")
    
    if key == 'maps':
        from services.scraper_runner import stop_maps_scraper
        stop_maps_scraper(camp_id)
    elif key == 'ads':
        from services.sniper_runner import stop_sniper
        stop_sniper()
    elif key == 'fb_ads':
        from services.sniper_runner import stop_fb_ads_scraper
        stop_fb_ads_scraper()
    elif key == 'tech':
        from services.sniper_runner import stop_ecom_scraper
        stop_ecom_scraper()
    elif key == 'jobs':
        from services.sniper_runner import stop_jobs_scraper
        stop_jobs_scraper()
    elif key == 'audit':
        from agents.auditeur.agent import auditeur_agent
        auditeur_agent.stop()
    elif key == 'enrichment':
        from agents.enrichisseur.agent import enrichisseur_agent
        enrichisseur_agent.stop()
        
    return jsonify({"ok": True, "message": f"Arrêt demandé pour {key}"})


@campaigns_bp.route('/api/scraper/force-stop', methods=['POST'])
def api_scraper_force_stop():
    """Tue brutalement une tâche selon sa clé et synchronise la DB."""
    from services.campaign_tracker import reset_all_active_campaigns
    data = request.get_json(silent=True, force=True) or {}
    key = data.get('key') or data.get('source') or 'maps'
    camp_id = data.get('campaign_id')
    
    logger.warning(f"[scraper_force_stop] KILL demandé pour {key} (camp_id={camp_id})")
    
    # ── Force DB reset pour synchroniser l'UI (Watchdog) ──────────────────
    reset_all_active_campaigns(reason=f"Force Stop ({key})")
    
    if key == 'maps':
        from services.scraper_runner import force_stop_maps_scraper
        force_stop_maps_scraper(camp_id)
    elif key in ['ads', 'fb_ads', 'tech', 'jobs']:
        from services.sniper_runner import force_stop_sniper
        force_stop_sniper()
    elif key == 'audit':
        from agents.auditeur.agent import auditeur_agent
        auditeur_agent.stop()
    elif key == 'enrichment':
        from agents.enrichisseur.agent import enrichisseur_agent
        enrichisseur_agent.stop()
        
    # Toujours tenter de tuer le navigateur en dernier recours
    try:
        from core.process_utils import kill_all_background_tasks
        killed_count = kill_all_background_tasks()
        logger.info(f"[scraper_force_stop] Cleanup global fini : {killed_count} processus tués.")
    except Exception as e:
        logger.error(f"[scraper_force_stop] Erreur lors du cleanup global: {e}")
        
    return jsonify({"ok": True, "message": f"Force Stop effectué (Nettoyage global lancé)"})




@campaigns_bp.route('/api/collectes')
def api_collectes():
    """Retourne les campagnes sous forme de collectes (sidebar filtres)."""
    try:
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT c.id, c.nom, c.secteur, c.ville, c.nb_demande,
                       COUNT(lb.id) AS leads_total
                FROM campagnes c
                LEFT JOIN leads_bruts lb ON lb.campaign_id = c.id
                GROUP BY c.id
                ORDER BY c.id DESC
                LIMIT 50
            """).fetchall()
        return jsonify({"collectes": [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@campaigns_bp.route('/api/planning/niche-stats')
def api_planning_niche_stats():
    """Statistiques agrégées par niche pour le planificateur."""
    try:
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT
                    c.secteur                               AS niche,
                    COUNT(DISTINCT c.id)                    AS campagnes,
                    COUNT(DISTINCT lb.id)                   AS leads_scrapes,
                    COUNT(DISTINCT ee.id)                   AS emails_envoyes,
                    COALESCE(SUM(ee.repondu), 0)            AS nb_reponses
                FROM campagnes c
                LEFT JOIN leads_bruts   lb ON lb.campaign_id = c.id
                LEFT JOIN emails_envoyes ee ON ee.lead_id    = lb.id
                WHERE c.secteur IS NOT NULL AND c.secteur != ''
                GROUP BY c.secteur
                ORDER BY emails_envoyes DESC
            """).fetchall()
        return jsonify({"stats": [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@campaigns_bp.route('/api/scraper/fill-quota', methods=['POST'])
def api_fill_quota():
    try:
        from auto_planner import fill_quota_if_needed, get_pipeline_count, get_auto_plan_settings
        settings = get_auto_plan_settings()
        pipeline = get_pipeline_count()
        deficit = max(0, settings['daily_quota'] - pipeline)
        if deficit == 0: return jsonify({'success': True, 'deficit': 0})
        fill_quota_if_needed(trigger_immediate=True)
        return jsonify({'success': True, 'deficit': deficit})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
