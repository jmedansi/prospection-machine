# -*- coding: utf-8 -*-
"""
dashboard/scheduler.py
Planificateur APScheduler — scraping automatique + envoi emails quotidien.
Utilise PipelineRegistry pour la découverte modulaire des tâches.
"""
import os
import logging
import threading
from datetime import date, datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

import sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT)
from database.db_manager import get_conn
from core.pipeline_registry import registry

logger = logging.getLogger(__name__)
_scheduler = None

# --- Logique de Log ---
def _log_job(job_id: str):
    try:
        with get_conn() as conn:
            conn.execute("INSERT OR REPLACE INTO scheduler_log (job_id, run_date, ran_at) VALUES (?, date('now'), datetime('now'))", (job_id,))
            conn.commit()
    except Exception as e: logger.error(f"[SCHEDULER] log error: {e}")

def _job_ran_today(job_id: str) -> bool:
    try:
        with get_conn() as conn:
            row = conn.execute("SELECT 1 FROM scheduler_log WHERE job_id=? AND run_date=date('now')", (job_id,)).fetchone()
        return row is not None
    except: return False

# --- Quota et Stats ---
def get_daily_quota() -> int:
    try:
        with get_conn() as conn:
            rows = {r['key']: r['value'] for r in conn.execute("SELECT key, value FROM planning_settings").fetchall()}
        start = date.fromisoformat(rows.get('quota_start_date', date.today().isoformat()))
        days = (date.today() - start).days
        conf = int(rows.get('daily_quota', 100))
        if days < 7: return min(50, conf)
        if days < 14: return min(100, conf)
        return conf
    except: return 30

def get_emails_sent_today() -> int:
    try:
        with get_conn() as conn:
            r = conn.execute("SELECT COUNT(*) as n FROM emails_envoyes WHERE date(date_envoi) = date('now')").fetchone()
            return r['n'] if r else 0
    except: return 0

# --- Jobs Core ---
def run_planned_scrapings():
    today = date.today().isoformat()
    try:
        with get_conn() as conn:
            campaigns = conn.execute("SELECT * FROM planned_campaigns WHERE date_planifiee=? AND statut='planned'", (today,)).fetchall()
        for c in campaigns:
            campaign_name = f"{c['secteur']} {c['city']} {today}"
            limit = c.get('limit_leads', 50)
            source = c.get('source', 'maps')
            
            success, res = False, None
            if source == 'sniper_ads':
                from services.sniper_runner import launch_sniper
                kw = c['keyword']
                if c['city'] and c['city'].lower() not in kw.lower():
                    kw = f"{kw} {c['city']}"
                success, res = launch_sniper(
                    keywords=[kw], country='fr', max_per_kw=limit, parallel_enrich=3, campaign_name=campaign_name
                )
                if success: res = None
            elif source == 'sniper_fb':
                from services.sniper_runner import launch_fb_ads_scraper
                kw = c['keyword']
                if c['city'] and c['city'].lower() not in kw.lower():
                    kw = f"{kw} {c['city']}"
                success, res = launch_fb_ads_scraper(
                    search_terms=[kw], country='FR', max_pages=5, parallel=3, campaign_name=campaign_name
                )
                if success: res = None
            elif source == 'sniper_ecom':
                from services.sniper_runner import launch_tech_scraper
                kw = c['keyword']
                if c['city'] and c['city'].lower() not in kw.lower():
                    kw = f"{kw} {c['city']}"
                success, res = launch_tech_scraper(
                    keywords=[kw], max_companies=limit*2, max_leads=limit, parallel=3, campaign_name=campaign_name
                )
                if success: res = None
            else: # maps
                from services.scraper_runner import launch_scraper
                success, res = launch_scraper(c['keyword'], c['city'], c['secteur'], limit=limit, campaign_name=campaign_name)

            if success:
                with get_conn() as conn:
                    if res:
                        conn.execute("UPDATE planned_campaigns SET statut='running', campaign_id=? WHERE id=?", (res, c['id']))
                    else:
                        conn.execute("UPDATE planned_campaigns SET statut='running' WHERE id=?", (c['id'],))
                    conn.commit()
        _log_job('planned_scrapings')
    except Exception as e: logger.error(f"[SCHEDULER] planned_scrapings: {e}")

def run_fill_check():
    """Vérification des batches (Phase 4 Logic)."""
    try:
        from dashboard.pipeline import maintain_batch_slots, notify_new_audits, auto_approve_after_timeout
        maintain_batch_slots()
        notify_new_audits()
        auto_approve_after_timeout()
    except Exception as e: logger.error(f"[SCHEDULER] fill_check: {e}")

def run_sequence_relances():
    """Exécute le worker de relances."""
    try:
        from workers.sequence_worker import run_sequence_worker
        run_sequence_worker()
    except Exception as e: logger.error(f"[SCHEDULER] sequence_relances: {e}")

def cruise_control_manager():
    """Auto-Pilot (Phase 3.1): lance une campagne si le quota n'est pas atteint."""
    try:
        quota = get_daily_quota()
        sent_today = get_emails_sent_today()
        
        # S'il reste de la place pour de nouveaux prospects
        if sent_today < quota:
            from scraper.sniper.keyword_bank import get_daily_batch
            # On prend 1 keyword au hasard
            kws = get_daily_batch(1)
            if not kws:
                return
            kw = kws[0]
            campaign_name = f"AutoPilot {kw} {date.today().isoformat()}"
            
            # Lancer le scraper sniper
            from services.sniper_runner import launch_sniper
            success, res = launch_sniper(
                keywords=[kw], country='fr', max_per_kw=20, parallel_enrich=3, campaign_name=campaign_name
            )
            logger.info(f"[CRUISE CONTROL] Lancé campagne auto: {campaign_name}")
            _log_job('cruise_control')
    except Exception as e:
        logger.error(f"[CRUISE CONTROL] erreur: {e}")

def run_startup_catchup():
    now = datetime.now()
    # Le planned scraping est désactivé. Conserver uniquement le contrôle de remplissage.
    run_fill_check()

def init_scheduler(_app=None):
    global _scheduler
    if _scheduler and _scheduler.running: return _scheduler

    _scheduler = BackgroundScheduler(timezone='Europe/Paris')

    # Core Jobs
    # _scheduler.add_job(run_planned_scrapings, CronTrigger(hour=6, minute=0), id='planned_scrapings')
    _scheduler.add_job(run_fill_check, CronTrigger(minute='*/15'), id='fill_check')
    _scheduler.add_job(run_sequence_relances, CronTrigger(hour=10, minute=30), id='sequence_relances')
    # _scheduler.add_job(cruise_control_manager, CronTrigger(hour='9-18', minute=0), id='cruise_control')

    # Sniper — IMAP polling (détection réponses step 1 toutes les 15 min)
    def _run_imap_poll():
        try:
            from sniper.imap_poller import run_poll
            run_poll(lookback_hours=48)
        except Exception as e:
            logger.error(f"[scheduler] imap_poller erreur : {e}")

    _scheduler.add_job(_run_imap_poll, CronTrigger(minute='*/15'), id='sniper_imap_poll')

    # Sniper — Relier la validation Telegram "OK" vers l'envoi Step 2
    def _check_telegram_step2():
        try:
            import sqlite3
            import traceback
            db_file = os.path.join("D:\\", "hub_telegram", "pending.db")
            if not os.path.exists(db_file): return
            
            conn = sqlite3.connect(db_file)
            rows = conn.execute("SELECT callback_id FROM pending WHERE status='ok' AND callback_id LIKE 'sniper_step2_%'").fetchall()
            
            if rows:
                from sniper.imap_poller import send_step2
                for row in rows:
                    cb_id = row[0]
                    # callback_id format : "sniper_step2_42"
                    try:
                        audit_id = int(cb_id.split('_')[-1])
                        # L'envoi gère déjà l'idempotence (si déjà envoyé, retourne False)
                        send_step2(audit_id)
                        # On marque comme complété dans hub_telegram pour ne plus le traiter
                        conn.execute("UPDATE pending SET status='completed' WHERE callback_id=?", (cb_id,))
                    except Exception as loop_e:
                        logger.error(f"[scheduler] _check_telegram_step2 parsing info {cb_id}: {loop_e}")
                conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"[scheduler] _check_telegram_step2 erreur : {e}\n{traceback.format_exc()}")

    # Vérification toutes les 2 minutes pour la réactivité
    _scheduler.add_job(_check_telegram_step2, IntervalTrigger(minutes=2), id='telegram_step2_poll')

    # Sniper / Maps — Poller validation Telegram pour les relances
    def _check_relance_approvals():
        try:
            import sqlite3
            db_file = os.path.join("D:\\", "hub_telegram", "pending.db")
            if not os.path.exists(db_file): return

            conn = sqlite3.connect(db_file)
            rows = conn.execute(
                "SELECT callback_id FROM pending WHERE status='ok' AND callback_id LIKE 'relance_approve_%'"
            ).fetchall()

            if rows:
                from services.email_sequence_service import EmailSequenceService
                seq_service = EmailSequenceService()
                for row in rows:
                    cb_id = row[0]
                    try:
                        sequence_id = int(cb_id.split('_')[-1])
                        ok = seq_service.approve_and_send(sequence_id)
                        if ok:
                            conn.execute("UPDATE pending SET status='completed' WHERE callback_id=?", (cb_id,))
                        else:
                            conn.execute("UPDATE pending SET status='failed' WHERE callback_id=?", (cb_id,))
                    except Exception as loop_e:
                        logger.error(f"[scheduler] _check_relance_approvals parsing {cb_id}: {loop_e}")
                conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"[scheduler] _check_relance_approvals erreur : {e}")

    _scheduler.add_job(_check_relance_approvals, IntervalTrigger(minutes=2), id='relance_approval_poll')

    # Sniper — Génération des emails (leads en attente → leads_audites)
    def _run_sniper_generate():
        try:
            from database.db_manager import get_conn as _gc
            with _gc() as c:
                row = c.execute(
                    "SELECT value FROM planning_settings WHERE key='sniper_auto_generate'"
                ).fetchone()
            if row and row["value"] == "1":
                from sniper.email_generator import generate_sniper_emails_batch
                generate_sniper_emails_batch(limit=100)
        except Exception as e:
            logger.error(f"[scheduler] sniper_generate erreur : {e}")

    _scheduler.add_job(_run_sniper_generate, CronTrigger(hour=8, minute=0), id='sniper_generate')

    # Sniper — Envoi step 1 (leads approuvés → Resend, quota dédié)
    def _run_sniper_send():
        try:
            from database.db_manager import get_conn as _gc
            with _gc() as c:
                row = c.execute(
                    "SELECT value FROM planning_settings WHERE key='sniper_auto_send'"
                ).fetchone()
            if row and row["value"] == "1":
                from services.sniper_sender_service import send_sniper_step1
                send_sniper_step1()
        except Exception as e:
            logger.error(f"[scheduler] sniper_send erreur : {e}")

    _scheduler.add_job(_run_sniper_send, CronTrigger(hour=8, minute=30), id='sniper_send')

    # Sniper — Scraping Google Ads quotidien (9h00, VPN requis)
    def _run_sniper_ads_daily():
        try:
            from database.db_manager import get_conn as _gc
            with _gc() as c:
                row = c.execute(
                    "SELECT value FROM planning_settings WHERE key='sniper_ads_auto_scrape'"
                ).fetchone()
            if not row or row["value"] != "1":
                return
            from scraper.sniper.keyword_bank import get_daily_batch
            from services.sniper_runner import launch_sniper, get_sniper_status
            if get_sniper_status()["running"]:
                logger.info("[scheduler] sniper_ads_daily ignoré — pipeline déjà actif")
                return
            keywords = get_daily_batch(n=10)
            logger.info(f"[scheduler] sniper_ads_daily — {len(keywords)} mots-clés : {keywords[:3]}...")
            launch_sniper(keywords=keywords, country="fr")
        except Exception as e:
            logger.error(f"[scheduler] sniper_ads_daily erreur : {e}")

    # _scheduler.add_job(_run_sniper_ads_daily, CronTrigger(hour=7, minute=0), id='sniper_ads_daily')

    # Sniper — Scraping E-com quotidien (08h00, après le job Ads)
    def _run_sniper_ecom_daily():
        try:
            from database.db_manager import get_conn as _gc
            with _gc() as c:
                row = c.execute(
                    "SELECT value FROM planning_settings WHERE key='sniper_ecom_auto_scrape'"
                ).fetchone()
            if not row or row["value"] != "1":
                return
            from scraper.sniper.keyword_bank import get_ecom_daily_batch
            from scraper.sniper.ecom_scraper import EcomScraper, get_state
            if get_state()["running"]:
                logger.info("[scheduler] sniper_ecom_daily ignoré — EcomScraper déjà actif")
                return
            keywords = get_ecom_daily_batch(n=8)
            logger.info(f"[scheduler] sniper_ecom_daily — {len(keywords)} mots-clés : {keywords[:3]}...")

            def _run():
                s = EcomScraper()
                s.run(keywords=keywords, country="fr", max_domains=200, max_leads=50)

            threading.Thread(target=_run, daemon=True, name="ecom_daily").start()
        except Exception as e:
            logger.error(f"[scheduler] sniper_ecom_daily erreur : {e}")

    # _scheduler.add_job(_run_sniper_ecom_daily, CronTrigger(hour=8, minute=0), id='sniper_ecom_daily')

    # CEO — Retry enrichissement pour les leads sans CEO (toutes les 2h)
    def _run_ceo_retry():
        try:
            with get_conn() as conn:
                rows = conn.execute("""
                    SELECT lb.id, lb.nom, lb.site_web
                    FROM leads_bruts lb
                    JOIN leads_audites la ON la.lead_id = lb.id
                    WHERE la.ceo_source = 'quota_error'
                      AND lb.statut NOT IN ('archive', 'bounced', 'desabonne')
                      AND lb.site_web IS NOT NULL AND lb.site_web != ''
                    LIMIT 20
                """).fetchall()

            if not rows:
                return

            logger.info(f"[scheduler] ceo_retry — {len(rows)} leads à ré-enrichir")

            from sniper.enrichment.ceo_finder import find_ceo
            import re as _re

            for row in rows:
                lead_id = row["id"]
                domain_raw = row["site_web"] or ""
                domain = _re.sub(r"^https?://(www\.)?", "", domain_raw).rstrip("/").split("/")[0]
                ceo = find_ceo(row["nom"] or "", domain, row["site_web"])

                if ceo.get("ceo_prenom"):
                    with get_conn() as conn:
                        conn.execute("""
                            UPDATE leads_audites
                            SET ceo_prenom = ?, ceo_nom = ?, ceo_source = ?
                            WHERE lead_id = ?
                        """, (ceo["ceo_prenom"], ceo["ceo_nom"], ceo["ceo_source"], lead_id))
                        conn.commit()
                    logger.info(
                        f"[scheduler] ceo_retry lead #{lead_id} → "
                        f"{ceo['ceo_prenom']} {ceo['ceo_nom']} ({ceo['ceo_source']})"
                    )

        except Exception as e:
            logger.error(f"[scheduler] ceo_retry erreur : {e}")

    _scheduler.add_job(_run_ceo_retry, IntervalTrigger(hours=2), id='ceo_retry')

    # Sauvegarde DB locale toutes les 5 heures
    def _run_db_backup_local():
        try:
            from backup_db import run_backup
            run_backup(git=False)
        except Exception as e:
            logger.error(f"[scheduler] db_backup_local erreur : {e}")

    _scheduler.add_job(_run_db_backup_local, CronTrigger(hour='*/5', minute=0), id='db_backup_local')

    # Sauvegarde complète de la machine et push GitHub quotidien (à 22h00)
    def _run_daily_git_backup():
        try:
            from backup_db import run_backup
            run_backup(git=True)
        except Exception as e:
            logger.error(f"[scheduler] daily_git_backup erreur : {e}")

    _scheduler.add_job(_run_daily_git_backup, CronTrigger(hour=22, minute=0), id='daily_git_backup')

    # Enregistrement des pipelines via le Registry (Phase 4.3)
    from dashboard.pipeline import maintain_batch_slots, notify_new_audits, auto_approve_after_timeout
    registry.register("Batch Maintenance", maintain_batch_slots, interval_hours=1, description="Maintient les slots de batches Resend")
    registry.register("Telegram Notifications", notify_new_audits, interval_hours=1, description="Notifie des nouveaux audits")
    registry.register("Auto Approval", auto_approve_after_timeout, interval_hours=1, description="Approuve après 5h")
    registry.register("Sequence Relances", run_sequence_relances, interval_hours=1, description="Envoie les relances automatiques")

    for name, p in registry.get_all().items():
        _scheduler.add_job(p['func'], IntervalTrigger(hours=p['interval']), id=f"pipeline_{name.lower().replace(' ', '_')}")

    _scheduler.start()
    
    # Background loops
    # from dashboard.pipeline.scraper_loop import start_background_scraper
    # start_background_scraper()

    threading.Thread(target=run_startup_catchup, daemon=True).start()
    return _scheduler

def get_scheduler(): return _scheduler

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    init_scheduler()
    logger.info("[SCHEDULER] Planificateur Prospection démarré en mode autonome.")
    import time
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        logger.info("[SCHEDULER] Planificateur Prospection arrêté.")
