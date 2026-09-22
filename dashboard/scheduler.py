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
    """Vérification des batches (Phase 4 Logic). Décommissionné : tables legacy purgées."""
    pass


def run_sequence_relances():
    """Exécute le worker de relances. Décommissionné : relances gérées par le v2 (v2_send_relances)."""
    pass

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
    pass

def init_scheduler(_app=None):
    global _scheduler
    if _scheduler and _scheduler.running: return _scheduler

    _scheduler = BackgroundScheduler(timezone='Europe/Paris')

    # Core Jobs (le legacy fill_check/sequence_relances est décommissionné : tables purgées)

    # v2 — Réponses entrantes (IMAP) : mêmes réponses → a_traiter_humain, toutes les 15 min
    def _run_v2_reply_poll():
        try:
            from envoi.reply_poller import run_poll
            res = run_poll(lookback_hours=48)
            if res.get('total_reponses'):
                logger.info("[scheduler] v2_reply_poll: %s réponse(s) détectée(s)", res['total_reponses'])
        except Exception as e:
            logger.error(f"[scheduler] v2_reply_poll erreur : {e}")

    _scheduler.add_job(_run_v2_reply_poll, CronTrigger(minute='*/15'), id='v2_reply_poll')

    # v2 — Relier la validation Telegram "OK" (objectifs.validation_telegram) vers l'envoi initial
    def _check_v2_approvals():
        try:
            import sqlite3
            from core.config import HUB_TELEGRAM
            db_file = os.path.join(HUB_TELEGRAM, "pending.db")
            if not os.path.exists(db_file): return

            conn = sqlite3.connect(db_file)
            rows = conn.execute(
                "SELECT callback_id FROM pending WHERE status='ok' AND callback_id LIKE 'v2_approve_%'"
            ).fetchall()

            if rows:
                from envoi import sequence_engine
                for row in rows:
                    cb_id = row[0]
                    try:
                        prospect_id = int(cb_id.split('_')[-1])
                        res = sequence_engine.approve_and_send_initial(prospect_id)
                        status = 'failed'
                        if res.get('success'):
                            status = 'completed'
                        elif res.get('status') in ('absent', 'sans_demande', 'validation_refusee', 'deja_envoye', 'deja_en_flux'):
                            status = 'failed'
                        conn.execute("UPDATE pending SET status=? WHERE callback_id=?", (status, cb_id))
                        if status == 'failed':
                            logger.info(f"[v2-poll] {cb_id} → {res.get('status')} (« {res.get('message')} »)")
                    except Exception as loop_e:
                        logger.error(f"[v2-poll] parsing {cb_id}: {loop_e}")
                conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"[v2-poll] erreur : {e}")
            import traceback
            logger.error(traceback.format_exc())

    _scheduler.add_job(_check_v2_approvals, IntervalTrigger(minutes=1), id='v2_approval_poll')

    # v2 — Envoi automatique des initials (kill-switch global + envoi_auto par objectif)
    def _run_v2_send_initial():
        try:
            from core.orchestration import run_auto_send
            res = run_auto_send()
            if res.get('runs'):
                logger.info(
                    "[v2-auto-send] %s objectif(s), %s envoi(s) tenté(s) (quota global: %s)",
                    len(res['runs']), res.get('total'), res.get('quoted', 'n/a'),
                )
        except Exception as e:
            logger.error(f"[v2-auto-send] erreur : {e}")
            import traceback
            logger.error(traceback.format_exc())

    _scheduler.add_job(_run_v2_send_initial, IntervalTrigger(minutes=5), id='v2_send_initial')

    # v2 — Relances dues (positions > 0, delai_jours) — mêmes règles global/objectif.
    # Campagnes `validation_relances=1` : un seul ✅ Telegram par liste (lot) demandé
    # par `ensure_batch_requests` ; l'envoi réel est déclenché par le poller
    # `v2_batch_poll` après approbation (`consume_approvals`).
    def _run_v2_send_relances():
        try:
            from core import orchestration, relance_batch_validator
            batch_camps = orchestration.enabled_campagnes()
            batch_ids = {c['id'] for c in batch_camps if c.get('validation_relances')}
            if batch_ids:
                res = relance_batch_validator.ensure_batch_requests()
                logger.info(
                    "[v2-relances] %s lot(s) validé(s) Telegram demandé(s) (success=%s)",
                    len(res.get('requests', [])), res.get('success'),
                )
            for camp in orchestration.enabled_campagnes():
                if camp['id'] in batch_ids:
                    continue  # envoi après ✅ du lot, pas d'auto-send
                res = orchestration.run_relances(camp['id'])
                if res.get('runs'):
                    logger.info(
                        "[v2-relances] campagne %s : %s relance(s) tentée(s)",
                        camp['id'], res.get('total'),
                    )
        except Exception as e:
            logger.error(f"[v2-relances] erreur : {e}")
            import traceback
            logger.error(traceback.format_exc())

    _scheduler.add_job(_run_v2_send_relances, IntervalTrigger(minutes=10), id='v2_send_relances')

    # v2 — Consommation des réponses ✅/❌ des LOTS de relances (campagnes
    # validation_relances=1) : ✅ → run_relances(liste, approval='auto'), ❌ → refuse.
    def _run_v2_batch_poll():
        try:
            from core.relance_batch_validator import consume_approvals
            res = consume_approvals()
            if res.get('consumed'):
                logger.info(
                    "[v2-batch-poll] %s lot(s) traité(s) : %s",
                    len(res['consumed']),
                    ", ".join(f"{c['callback_id']}→{c['statut']}" for c in res['consumed']),
                )
        except Exception as e:
            logger.error(f"[v2-batch-poll] erreur : {e}")
            import traceback
            logger.error(traceback.format_exc())

    _scheduler.add_job(_run_v2_batch_poll, IntervalTrigger(minutes=1), id='v2_batch_poll')

    # v2 — Remise à zéro quotidienne des quotas boîtes (usage_jour), 00:05
    def _reset_daily_quotas():
        try:
            from envoi.gateway import reset_daily_quotas
            n = reset_daily_quotas()
            if n:
                logger.info("[scheduler] quotas boîtes remis à 0 (%s boîte(s))", n)
        except Exception as e:
            logger.error(f"[scheduler] reset quotas erreur : {e}")

    _scheduler.add_job(_reset_daily_quotas, CronTrigger(hour=0, minute=5), id='reset_daily_quotas')

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

    # CEO — Retry enrichissement pour les leads sans CEO — DÉCOMMISSIONNÉ (pipeline v1)
    # (lisait leads_bruts / leads_audites, table legacy v1)

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

    # ─── Rappels Telegram pour listes contactées (J+3 / J+7 / J+14) — DÉCOMMISSIONNÉ
    # (lisait lead_lists, table legacy v1 ; modèle v2 = listes/prospects par campagne)

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
