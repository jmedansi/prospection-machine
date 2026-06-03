# -*- coding: utf-8 -*-
"""
scraper/sniper/fb_ads_extractor.py — Meta Ad Library API client

Collecte les annonceurs actifs sur Facebook/Instagram via l'API officielle.
Enrichit chaque annonceur avec son site web (2ème appel API par page_id).

Usage :
    from scraper.sniper.fb_ads_extractor import extract_fb_ads
    leads = extract_fb_ads(["restaurant", "boutique mode"], country="FR", max_pages=5)
"""

import logging
import os
import time
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

_API_BASE   = "https://graph.facebook.com/v19.0"
_AD_ARCHIVE = f"{_API_BASE}/ads_archive"

# Plateformes non exploitables comme site web
_SOCIAL_DOMAINS = {
    "facebook.com", "instagram.com", "linkedin.com", "twitter.com",
    "tiktok.com", "youtube.com", "linktr.ee", "linktree.com",
    "bio.link", "beacons.ai", "carrd.co",
}

# Paramètres d'une requête Ad Library
_AD_FIELDS = ",".join([
    "id",
    "page_name",
    "page_id",
    "ad_creative_bodies",
    "ad_delivery_start_time",
    "publisher_platforms",
])

# Champs récupérés sur la Page pour obtenir le site
_PAGE_FIELDS = "name,website,category,fan_count"


def _get_token() -> str:
    token = os.getenv("FB_ADS_ACCESS_TOKEN", "")
    if not token:
        raise EnvironmentError("FB_ADS_ACCESS_TOKEN manquant dans .env")
    return token


def _is_social_url(url: str) -> bool:
    """Retourne True si l'URL pointe vers un réseau social (non exploitable)."""
    try:
        netloc = urlparse(url).netloc.lower().lstrip("www.")
        return any(netloc == d or netloc.endswith("." + d) for d in _SOCIAL_DOMAINS)
    except Exception:
        return False


def _fetch_page_info(page_id: str, token: str) -> Dict:
    """Récupère le site web et la catégorie d'une Page Facebook."""
    try:
        r = requests.get(
            f"{_API_BASE}/{page_id}",
            params={"fields": _PAGE_FIELDS, "access_token": token},
            timeout=10,
        )
        data = r.json()
        if "error" in data:
            logger.debug(f"Page {page_id} erreur: {data['error'].get('message')}")
            return {}
        return {
            "page_name":  data.get("name", ""),
            "site_web":   data.get("website", "") or "",
            "category":   data.get("category", ""),
            "fan_count":  data.get("fan_count", 0),
        }
    except Exception as e:
        logger.debug(f"_fetch_page_info {page_id}: {e}")
        return {}


def extract_fb_ads(
    search_terms:  List[str],
    country:       str = "FR",
    max_pages:     int = 5,
    limit_per_req: int = 50,
    ad_type:       str = "ALL",
) -> List[Dict]:
    """
    Extrait les annonceurs actifs depuis la Meta Ad Library.

    Args:
        search_terms:  mots-clés de recherche dans les pubs
        country:       code ISO pays ('FR', 'BE', 'CH', 'LU')
        max_pages:     nombre max de pages de résultats par mot-clé
        limit_per_req: résultats par requête (max 50)
        ad_type:       'ALL' | 'POLITICAL_AND_ISSUE_ADS'

    Returns:
        Liste de dicts :
        {
            "page_id":    str,
            "page_name":  str,
            "site_web":   str | None,   # None = pas de site
            "has_site":   bool,
            "category":   str,
            "fan_count":  int,
            "ad_body":    str,          # corps de la 1ère pub trouvée
            "ad_start":   str,          # date début pub
            "mot_cle":    str,
            "pays":       str,
        }
    """
    token   = _get_token()
    results = []
    seen_pages: set = set()

    for kw in search_terms:
        logger.info(f"Ad Library — recherche '{kw}' pays={country}")
        cursor = None
        page_count = 0

        while page_count < max_pages:
            params: Dict = {
                "ad_reached_countries": f"['{country}']",
                "search_terms":         kw,
                "ad_type":              ad_type,
                "fields":               _AD_FIELDS,
                "limit":                limit_per_req,
                "access_token":         token,
            }
            if cursor:
                params["after"] = cursor

            try:
                r = requests.get(_AD_ARCHIVE, params=params, timeout=20)
                data = r.json()
            except Exception as e:
                logger.error(f"Ad Library requête échouée pour '{kw}': {e}")
                break

            if "error" in data:
                err = data["error"]
                logger.error(f"Ad Library API erreur: {err.get('message')} (code {err.get('code')})")
                break

            ads = data.get("data", [])
            logger.info(f"  Page {page_count + 1} — {len(ads)} pubs reçues")

            new_this_page = 0
            for ad in ads:
                pid = str(ad.get("page_id", ""))
                if not pid or pid in seen_pages:
                    continue
                seen_pages.add(pid)
                new_this_page += 1

                # Récupérer infos de la Page (site web, catégorie)
                page_info = _fetch_page_info(pid, token)
                time.sleep(0.2)  # respect rate limit

                site = page_info.get("site_web", "").strip()
                has_site = bool(site) and not _is_social_url(site)

                # Corps de la première pub (pour contexte copywriting)
                bodies = ad.get("ad_creative_bodies") or []
                ad_body = bodies[0] if bodies else ""

                results.append({
                    "page_id":   pid,
                    "ad_id":     ad.get("id", ""),
                    "page_name": page_info.get("page_name") or ad.get("page_name", ""),
                    "site_web":  site if has_site else None,
                    "has_site":  has_site,
                    "category":  page_info.get("category", ""),
                    "fan_count": page_info.get("fan_count", 0),
                    "ad_body":   ad_body[:300] if ad_body else "",
                    "ad_start":  ad.get("ad_delivery_start_time", ""),
                    "mot_cle":   kw,
                    "pays":      country,
                })

            if new_this_page == 0:
                logger.info(f"  Page {page_count + 1} — aucun nouvel annonceur, arrêt de la pagination.")
                break

            # Pagination
            paging = data.get("paging", {})
            cursor = paging.get("cursors", {}).get("after")
            if not cursor or not paging.get("next"):
                break

            page_count += 1
            time.sleep(1)  # pause entre pages

        logger.info(f"  '{kw}' → {len([r for r in results if r['mot_cle'] == kw])} annonceurs uniques")

    logger.info(f"Total annonceurs Meta extraits : {len(results)}")
    return results
