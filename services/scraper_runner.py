# -*- coding: utf-8 -*-
"""
services/scraper_runner.py
Gère le lancement des scrapings en arrière-plan.
Intègre le campaign_tracker pour le suivi d'état.
Utilise un thread in-process (pas de subprocess) pour éviter les problèmes CDP.
"""
import os
import sys
import threading
import asyncio
import logging
from services.campaign_tracker import (
    create_campaign, start_campaign, complete_campaign, fail_campaign
)

logger = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def launch_scraper(keyword, city, sector=None, limit=50, min_emails=10, campaign_name=None, min_reviews=0, multi_zone=False,
                   country='fr', require_contact=False, keyword_variants=False, site_filter='all'):
    """
    Lance le scraper Maps en arrière-plan (in-process dans un thread daemon).
    Crée la campagne en DB AVANT le lancement, puis track la progression.
    """
    try:
        if not campaign_name:
            campaign_name = f"{sector or keyword} {city}"
            
        camp_id = create_campaign(campaign_name, secteur=sector or keyword, ville=city, source='maps', nb_demande=limit,
                                  pays=country)
        start_campaign(camp_id, phase='scraping')

        # Récupérer l'offset depuis la campagne (reprise après crash)
        offset = 0
        try:
            from services.campaign_tracker import get_campaign_state
            state = get_campaign_state(camp_id)
            if state and state.get('progress', {}).get('processed'):
                offset = state['progress']['processed']
                if offset and offset > 0:
                    logger.info(f"[scraper_runner] Reprise campagne #{camp_id} offset={offset}")
        except Exception:
            pass

        # ── Lancement in-process dans un thread daemon ───────────────────
        def _run():
            try:
                from scraper.main import main_async

                argv = [
                    '--keyword', keyword,
                    '--city', city,
                    '--limit', str(limit),
                    '--min-emails', str(min_emails),
                    '--campaign-id', str(camp_id),
                    '--min-reviews', str(min_reviews),
                    '--secteur', str(sector or ''),
                    '--country', str(country),
                ]
                if require_contact:
                    argv.append('--require-contact')
                if keyword_variants:
                    argv.append('--keyword-variants')
                if multi_zone:
                    argv.append('--multi-zone')
                if site_filter and site_filter != 'all':
                    argv.extend(['--site-filter', site_filter])
                if offset > 0:
                    argv.extend(['--offset', str(offset)])

                asyncio.run(main_async(argv))
                complete_campaign(camp_id)
            except Exception as e:
                logger.error(f"[scraper_runner] thread error: {e}")
                fail_campaign(camp_id, str(e), phase='scraping')

        thread = threading.Thread(target=_run, daemon=True, name=f"maps-scraper-{camp_id}")
        thread.start()

        return True, camp_id
    except Exception as e:
        logger.error(f"Error services/scraper_runner.launch_scraper: {e}")
        return False, str(e)


def stop_maps_scraper(camp_id=None):
    """Arrête proprement le scraper Maps via le flag (utilisé par le dashboard)."""
    import os
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    stop_flag = os.path.join(ROOT, 'data', 'maps_stop.flag')
    try:
        os.makedirs(os.path.dirname(stop_flag), exist_ok=True)
        with open(stop_flag, 'w') as f:
            f.write('stop')
        return True
    except: return False

def force_stop_maps_scraper(camp_id=None):
    """Force stop du scraper Maps et reset DB."""
    from services.campaign_tracker import reset_all_active_campaigns
    from core.process_utils import kill_all_background_tasks
    
    reset_all_active_campaigns(reason="Force Stop (Maps)")
    
    killed = kill_all_background_tasks()
    logger.info(f"[scraper_runner] Force stop global effectué ({killed} processus)")
    return True
