# -*- coding: utf-8 -*-
"""
services/sniper_runner.py — Lanceur background du pipeline Sniper

Lance le pipeline dans un thread daemon pour ne pas bloquer Flask.
Expose launch_sniper() et get_sniper_status() utilisés par les routes API.
Intègre campaign_tracker pour le suivi d'état persistant.
"""

import logging
import threading
from typing import Dict, List, Optional
from services.campaign_tracker import (
    create_campaign, start_campaign, complete_campaign, fail_campaign
)

logger = logging.getLogger(__name__)

_thread:              Optional[threading.Thread] = None
_ecom_thread:         Optional[threading.Thread] = None
_jobs_thread:         Optional[threading.Thread] = None
_fb_ads_thread:       Optional[threading.Thread] = None
_transparency_thread: Optional[threading.Thread] = None

_DEFAULT_KW: List[str] = []   # placeholder pour éviter import circulaire dans les logs


def launch_sniper(
    keywords:        List[str],
    country:         str = "fr",
    city:            str = "",
    max_per_kw:      int = 9999,
    pages_per_kw:    int = 15,
    parallel_enrich: int = 3,
    campaign_name:   Optional[str] = None,
    min_leads:       int = 0,
    secteur:         str = "",
) -> tuple[bool, str]:
    """
    Lance le pipeline Sniper en arrière-plan.

    Returns:
        (True, "Lancé") ou (False, "message d'erreur")
    """
    global _thread

    from scraper.sniper.pipeline import get_state, reset_state, SniperPipeline

    if get_state()["running"]:
        if _thread and _thread.is_alive():
            return False, "Pipeline Sniper déjà en cours"
        reset_state()

    if not keywords:
        return False, "Liste de mots-clés vide"

    # ── Créer la campagne en DB ────────────────────────────────────────
    camp_name = campaign_name or f"Ads {', '.join(keywords[:3])} {city}".strip()
    try:
        camp_id = create_campaign(camp_name, secteur=keywords[0] if keywords else '', ville=city, source='ads', nb_demande=max_per_kw * len(keywords))
        start_campaign(camp_id, phase='scraping')
    except Exception as e:
        logger.error(f"[sniper] Erreur création campagne: {e}")
        camp_id = None

    def _run():
        try:
            pipeline = SniperPipeline()
            pipeline.run(
                keywords=keywords,
                country=country,
                city=city,
                max_per_kw=max_per_kw,
                pages_per_kw=pages_per_kw,
                parallel_enrich=parallel_enrich,
                campaign_name=campaign_name,
                min_leads=min_leads,
                secteur=secteur,
            )
            if camp_id:
                complete_campaign(camp_id)
        except Exception:
            logger.exception("sniper_runner thread error")
            if camp_id:
                fail_campaign(camp_id, "Exception non gérée dans le pipeline Sniper", phase='scraping')

    _thread = threading.Thread(target=_run, daemon=True, name="sniper-pipeline")
    _thread.start()

    logger.info(f"Pipeline Sniper lancé — {len(keywords)} mots-clés, pays={country}")
    return True, "Lancé"


def get_sniper_status() -> Dict:
    """Retourne l'état courant du pipeline (pollable par le dashboard)."""
    from scraper.sniper.pipeline import get_state
    return get_state()


# ─── Source 2 : E-Commerce Stack ─────────────────────────────────────────────



def launch_ecom_scraper(
    keywords:      Optional[List[str]] = None,
    city:          str = "",
    max_companies: int = 300,
    max_leads:     int = 50,
    parallel:      int = 3,
    campaign_name: Optional[str] = None,
    min_leads:     int = 0,
) -> tuple[bool, str]:
    global _ecom_thread

    from scraper.sniper.ecom_scraper import get_state as ecom_state, reset_state as ecom_reset

    if ecom_state()["running"]:
        if _ecom_thread and _ecom_thread.is_alive():
            return False, "EcomScraper déjà en cours"
        ecom_reset()

    # ── Créer la campagne en DB ────────────────────────────────────────
    camp_name = campaign_name or f"E-com {', '.join((keywords or [])[:3])} {city}".strip()
    try:
        camp_id = create_campaign(camp_name, secteur='ecom', ville=city, source='tech', nb_demande=max_leads)
        start_campaign(camp_id, phase='scraping')
    except Exception as e:
        logger.error(f"[ecom] Erreur création campagne: {e}")
        camp_id = None

    def _run():
        try:
            from scraper.sniper.ecom_scraper import EcomScraper
            EcomScraper().run(
                keywords=keywords,
                city=city,
                max_domains=max_companies,
                max_leads=max_leads,
                parallel=parallel,
                campaign_name=campaign_name,
                min_leads=min_leads,
            )
            if camp_id:
                complete_campaign(camp_id)
        except Exception:
            logger.exception("ecom_scraper thread error")
            if camp_id:
                fail_campaign(camp_id, "Exception EcomScraper", phase='scraping')

    _ecom_thread = threading.Thread(target=_run, daemon=True, name="ecom-scraper")
    _ecom_thread.start()

    logger.info(f"EcomScraper lancé — {len(keywords or [])} mots-clés, max {max_leads} leads")
    return True, "Lancé"


def get_ecom_status() -> Dict:
    from scraper.sniper.ecom_scraper import get_state
    return get_state()


# Alias legacy (anciens leads source='tech' toujours en DB)
launch_tech_scraper = launch_ecom_scraper
get_tech_status     = get_ecom_status


# ─── Source 3 : Jobs ─────────────────────────────────────────────────────────


def launch_jobs_scraper(
    keywords:          Optional[List[str]] = None,
    max_offers_per_kw: int = 50,
    days_back:         int = 7,
    max_leads:         int = 50,
    parallel:          int = 3,
    campaign_name:     Optional[str] = None,
) -> tuple[bool, str]:
    """
    Lance le JobsScraper en arrière-plan.

    Returns:
        (True, "Lancé") ou (False, "message d'erreur")
    """
    global _jobs_thread

    from scraper.sniper.jobs_scraper import get_state as jobs_state, reset_state as jobs_reset

    if jobs_state()["running"]:
        if _jobs_thread and _jobs_thread.is_alive():
            return False, "JobsScraper déjà en cours"
        jobs_reset()

    # ── Créer la campagne en DB ────────────────────────────────────────
    camp_name = campaign_name or f"Jobs {', '.join((keywords or [])[:3])}".strip()
    try:
        camp_id = create_campaign(camp_name, secteur='jobs', ville='', source='jobs', nb_demande=max_leads)
        start_campaign(camp_id, phase='scraping')
    except Exception as e:
        logger.error(f"[jobs] Erreur création campagne: {e}")
        camp_id = None

    def _run():
        try:
            from scraper.sniper.jobs_scraper import JobsScraper
            JobsScraper().run(
                keywords=keywords,
                max_offers_per_kw=max_offers_per_kw,
                days_back=days_back,
                max_leads=max_leads,
                parallel=parallel,
                campaign_name=campaign_name,
            )
            if camp_id:
                complete_campaign(camp_id)
        except Exception:
            logger.exception("jobs_scraper thread error")
            if camp_id:
                fail_campaign(camp_id, "Exception JobsScraper", phase='scraping')

    _jobs_thread = threading.Thread(target=_run, daemon=True, name="jobs-scraper")
    _jobs_thread.start()

    logger.info(f"JobsScraper lancé — {len(keywords or _DEFAULT_KW)} mots-clés")
    return True, "Lancé"


def get_jobs_status() -> Dict:
    """Retourne l'état courant du JobsScraper (pollable par le dashboard)."""
    from scraper.sniper.jobs_scraper import get_state
    return get_state()


# ─── Source 5 : Facebook Ad Library ──────────────────────────────────────────


def launch_fb_ads_scraper(
    search_terms:  List[str],
    country:       str = "FR",
    city:          str = "",
    max_pages:     int = 5,
    parallel:      int = 3,
    campaign_name: Optional[str] = None,
    min_leads:     int = 0,
) -> tuple[bool, str]:
    global _fb_ads_thread

    from scraper.sniper.fb_ads_pipeline import get_state as fb_state, reset_state as fb_reset

    if fb_state()["running"]:
        if _fb_ads_thread and _fb_ads_thread.is_alive():
            return False, "FB Ads pipeline déjà en cours"
        fb_reset()

    if not search_terms:
        return False, "Liste de mots-clés vide"

    # ── Créer la campagne en DB ────────────────────────────────────────
    camp_name = campaign_name or f"FB Ads {', '.join(search_terms[:3])} {city}".strip()
    try:
        camp_id = create_campaign(camp_name, secteur='fb_ads', ville=city, source='fb_ads', nb_demande=max_pages * len(search_terms) * 5)
        start_campaign(camp_id, phase='scraping')
    except Exception as e:
        logger.error(f"[fb_ads] Erreur création campagne: {e}")
        camp_id = None

    def _run():
        try:
            from scraper.sniper.fb_ads_pipeline import FbAdsPipeline
            FbAdsPipeline().run(
                search_terms=search_terms,
                country=country,
                city=city,
                max_pages=max_pages,
                parallel=parallel,
                campaign_name=campaign_name,
                min_leads=min_leads,
            )
            if camp_id:
                complete_campaign(camp_id)
        except Exception:
            logger.exception("fb_ads_runner thread error")
            if camp_id:
                fail_campaign(camp_id, "Exception FB Ads pipeline", phase='scraping')

    _fb_ads_thread = threading.Thread(target=_run, daemon=True, name="fb-ads-pipeline")
    _fb_ads_thread.start()

    logger.info(f"FB Ads pipeline lancé — {len(search_terms)} mots-clés, pays={country}")
    return True, "Lancé"


def get_fb_ads_status() -> Dict:
    from scraper.sniper.fb_ads_pipeline import get_state
    return get_state()


# ─── Source 6 : Google Ads Transparency Center ───────────────────────────────


def launch_transparency_scraper(
    keywords:        List[str],
    country:         str = "FR",
    max_per_kw:      int = 20,
    parallel_enrich: int = 3,
    campaign_name:   Optional[str] = None,
) -> tuple[bool, str]:
    global _transparency_thread

    from scraper.sniper.transparency_pipeline import get_state as tr_state, reset_state as tr_reset

    if tr_state()["running"]:
        if _transparency_thread and _transparency_thread.is_alive():
            return False, "Transparency pipeline déjà en cours"
        tr_reset()

    if not keywords:
        return False, "Liste de mots-clés vide"

    # ── Créer la campagne en DB ────────────────────────────────────────
    camp_name = campaign_name or f"Transparency {', '.join(keywords[:3])}".strip()
    try:
        camp_id = create_campaign(camp_name, secteur='ads', ville='', source='ads', nb_demande=max_per_kw * len(keywords))
        start_campaign(camp_id, phase='scraping')
    except Exception as e:
        logger.error(f"[transparency] Erreur création campagne: {e}")
        camp_id = None

    def _run():
        try:
            from scraper.sniper.transparency_pipeline import TransparencyPipeline
            TransparencyPipeline().run(
                keywords=keywords,
                country=country,
                max_per_kw=max_per_kw,
                parallel_enrich=parallel_enrich,
                campaign_name=campaign_name,
            )
            if camp_id:
                complete_campaign(camp_id)
        except Exception:
            logger.exception("transparency_runner thread error")
            if camp_id:
                fail_campaign(camp_id, "Exception Transparency pipeline", phase='scraping')

    _transparency_thread = threading.Thread(target=_run, daemon=True, name="transparency-pipeline")
    _transparency_thread.start()

    logger.info(f"Transparency pipeline lancé — {len(keywords)} mots-clés, pays={country}")
    return True, "Lancé"


def get_transparency_status() -> Dict:
    from scraper.sniper.transparency_pipeline import get_state
    return get_state()


# ─── Fonctions d'arrêt d'urgence ─────────────────────────────────────────────

def stop_sniper():
    """Demande l'arrêt du pipeline Sniper Ads."""
    try:
        from scraper.sniper.pipeline import request_stop
        request_stop()
        logger.info("Arrêt demandé pour le pipeline Sniper Ads")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de l'arrêt du pipeline: {e}")
        return False


def force_stop_sniper():
    """Arrêt d'urgence immédiat en fermant les onglets et tuant les processus."""
    try:
        from core.process_utils import kill_all_background_tasks
        from services.campaign_tracker import reset_all_active_campaigns
        
        # 1. Demander l'arrêt à tous les pipelines Sniper
        try:
            from scraper.sniper.pipeline import request_stop as rs1, reset_state as r1
            rs1(); r1()
        except Exception: pass
        
        try:
            from scraper.sniper.ecom_scraper import request_stop as rs2, reset_state as r2
            rs2(); r2()
        except Exception: pass
        
        try:
            from scraper.sniper.jobs_scraper import request_stop as rs3, reset_state as r3
            rs3(); r3()
        except Exception: pass
        
        try:
            from scraper.sniper.fb_ads_pipeline import request_stop as rs4, reset_state as r4
            rs4(); r4()
        except Exception: pass

        # 2. Tuer physiquement les processus (Chrome, etc.)
        killed = kill_all_background_tasks()
        
        # 3. Reset DB state to sync UI
        reset_all_active_campaigns(reason="Force Stop (Global)")
        
        logger.warning(f"FORCE STOP GLOBAL : {killed} tâches de fond arrêtées et états réinitialisés.")
        return True
    except Exception as e:
        logger.error(f"Erreur lors du force stop global: {e}")
        return False


def stop_ecom_scraper():
    """Demande l'arrêt de l'EcomScraper."""
    try:
        from scraper.sniper.ecom_scraper import request_stop
        request_stop()
        logger.info("Arrêt demandé pour l'EcomScraper")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de l'arrêt de l'EcomScraper: {e}")
        return False


def stop_jobs_scraper():
    """Demande l'arrêt du JobsScraper."""
    try:
        from scraper.sniper.jobs_scraper import request_stop
        request_stop()
        logger.info("Arrêt demandé pour le JobsScraper")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de l'arrêt du JobsScraper: {e}")
        return False


def stop_bodacc_scanner():
    """Demande l'arrêt du BODACC scanner."""
    try:
        from sniper.bodacc_scanner import request_stop
        request_stop()
        logger.info("Arrêt demandé pour le BODACC scanner")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de l'arrêt du BODACC scanner: {e}")
        return False


def stop_fb_ads_scraper():
    """Demande l'arrêt du FB Ads scraper."""
    try:
        from scraper.sniper.fb_ads_pipeline import request_stop
        request_stop()
        logger.info("Arrêt demandé pour le FB Ads scraper")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de l'arrêt du FB Ads scraper: {e}")
        return False


def stop_transparency_scraper():
    """Demande l'arrêt du Transparency scraper."""
    try:
        from scraper.sniper.transparency_pipeline import request_stop
        request_stop()
        logger.info("Arrêt demandé pour le Transparency scraper")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de l'arrêt du Transparency scraper: {e}")
        return False
