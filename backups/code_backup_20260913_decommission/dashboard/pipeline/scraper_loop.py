# -*- coding: utf-8 -*-
"""
dashboard/pipeline/scraper_loop.py
Boucle de scraping automatique pour maintenir le stock de leads.
"""
import os
import sys
import subprocess
import threading
import time
import logging
from datetime import date as dt_date
from database.db_manager import get_conn

logger = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BATCH_SIZE = 50

def get_available_leads_count(source: str = None) -> int:
    """Retourne le nombre de leads disponibles pour les batches, filtré par source."""
    try:
        with get_conn() as conn:
            query = """
                SELECT COUNT(*) as n FROM leads_bruts lb
                WHERE lb.email IS NOT NULL AND lb.email != ''
                  AND lb.statut NOT IN ('envoye', 'email_sent', 'scheduled')
                  AND lb.id NOT IN (
                      SELECT DISTINCT lead_id FROM emails_envoyes WHERE lead_id IS NOT NULL
                  )
                  AND lb.id NOT IN (
                      SELECT lead_id FROM leads_audites WHERE approuve = 1
                  )
            """
            if source:
                # Support simple match for sources (handles 'maps', 'ads', 'ecom', etc.)
                query += f" AND lb.source LIKE '%{source}%'"
                
            rows = conn.execute(query).fetchone()
            return rows['n'] if rows else 0
    except Exception as e:
        logger.error(f"[PIPELINE-Scraper] get_available_leads_count: {e}")
        return 0

def _run_source_scraping(source: str, needed_leads: int):
    """Lance le scraper approprié pour la source demandée."""
    try:
        from auto_planner import get_auto_plan_settings
        settings = get_auto_plan_settings()
        today = dt_date.today().isoformat()
        
        if source == 'maps':
            # Logic Google Maps existante (rotation via priorités)
            from auto_planner import get_next_priorities
            from database.campaigns import insert_campaign
            
            candidates = get_next_priorities(1, today)
            if not candidates: return
            c = candidates[0]
            
            campaign_name = f"Background Top-up: {c['keyword']} {c['ville']}"
            camp_id = insert_campaign(campaign_name, c.get('secteur', ''), c['ville'], nb_demande=needed_leads*4)
            
            cmd = [
                sys.executable, os.path.join(ROOT, 'scraper', 'main.py'),
                '--keyword', c['keyword'], '--city', c['ville'],
                '--min-emails', str(needed_leads), '--limit', str(needed_leads * 4),
                '--campaign-id', str(camp_id)
            ]
            
            log_file = os.path.join(ROOT, 'data', 'background_scraper.log')
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"\n--- {today} {time.strftime('%H:%M:%S')} | MAPS ---\n")
                subprocess.run(cmd, cwd=ROOT, stdout=f, stderr=f, timeout=5400)
                
            with get_conn() as conn:
                conn.execute("UPDATE scraping_priorities SET derniere_execution=? WHERE id=?", (today, c['id']))
                conn.commit()

        elif source == 'ads':
            from services.sniper_runner import launch_sniper
            from scraper.sniper.keyword_bank import get_daily_batch
            
            kws = get_daily_batch(n=10)
            campaign_name = f"Auto-Topup Ads {today}"
            logger.info(f"[PIPELINE-Scraper] Lancement Sniper Ads auto: {len(kws)} kws")
            launch_sniper(keywords=kws, min_leads=needed_leads, campaign_name=campaign_name)

        elif source == 'ecom':
            from services.sniper_runner import launch_ecom_scraper
            campaign_name = f"Auto-Topup Ecom {today}"
            logger.info(f"[PIPELINE-Scraper] Lancement Ecom auto: {needed_leads} leads")
            launch_ecom_scraper(max_leads=needed_leads, campaign_name=campaign_name)

    except Exception as e:
        logger.error(f"[PIPELINE-Scraper] _run_source_scraping({source}): {e}")

def background_scraper_loop():
    """Vérifie toutes les heures si le stock de leads est suffisant pour chaque source."""
    while True:
        try:
            from auto_planner import get_auto_plan_settings
            settings = get_auto_plan_settings()
            
            # 1. Maps (DÉSACTIVÉ COMPLETEMENT - Ne plus lancer de scraping Maps automatique seul)
            # if settings.get('maps_auto_scrape') in (True, '1', 1):
            #     quota = int(settings.get('maps_daily_quota', BATCH_SIZE))
            #     available = get_available_leads_count(source='maps')
            #     if available < quota:
            #         needed = (quota * 2) - available
            #         if needed > 0:
            #             logger.info(f"[PIPELINE-Scraper] Stock Maps faible ({available}/{quota}). Top-up de {needed}...")
            #             threading.Thread(target=_run_source_scraping, args=('maps', needed), daemon=True).start()

            # 2. Sniper Ads
            if settings.get('ads_auto_scrape', '0') == '1' or settings.get('sniper_ads_auto_scrape') == '1':
                quota = int(settings.get('ads_daily_quota', 20))
                available = get_available_leads_count(source='ads')
                if available < quota:
                    needed = (quota * 2) - available
                    if needed > 0:
                        logger.info(f"[PIPELINE-Scraper] Stock Ads faible ({available}/{quota}). Top-up de {needed}...")
                        threading.Thread(target=_run_source_scraping, args=('ads', needed), daemon=True).start()

            # 3. E-commerce
            if settings.get('ecom_auto_scrape', '0') == '1' or settings.get('sniper_ecom_auto_scrape') == '1':
                quota = int(settings.get('ecom_daily_quota', 20))
                available = get_available_leads_count(source='ecom')
                if available < quota:
                    needed = (quota * 2) - available
                    if needed > 0:
                        logger.info(f"[PIPELINE-Scraper] Stock Ecom faible ({available}/{quota}). Top-up de {needed}...")
                        threading.Thread(target=_run_source_scraping, args=('ecom', needed), daemon=True).start()

            time.sleep(3600)
        except Exception as e:
            logger.error(f"[PIPELINE-Scraper] loop error: {e}")
            time.sleep(300)

def _run_scraping_sync(min_emails: int):
    """Alias de compatibilité pour Maps."""
    _run_source_scraping('maps', min_emails)

def start_background_scraper():
    """Démarre le thread de scraping."""
    thread = threading.Thread(target=background_scraper_loop, daemon=True)
    thread.start()
    logger.info("[PIPELINE-Scraper] Thread démarré")
