# -*- coding: utf-8 -*-
"""
scraper/sniper/ecom_scraper.py — Source 2 : E-commerçants via Google Search

Lire scraper/sniper/README.md avant toute modification.

Deux flux parallèles :
  Source A — Annonces Google ("acheter X en ligne") → boutiques qui font déjà de la pub
             Argument : budget ads gaspillé si le site est lent
  Source B — Résultats organiques mêmes mots-clés → boutiques sans pub
             Argument : pénalisé Google Shopping, trafic perdu

Flux commun après collecte des domaines :
  Phase 2  → Wappalyzer     ← détecte le CMS / e-commerce / CDN
  Phase 3  → PageSpeed      ← seulement si CMS à budget signal
  Phase 4  → scoring.py     ← tag_urgence + niveau_urgence
  Phase 5  → DB             ← INSERT leads_bruts source='ecom'

Usage programmatique :
    from scraper.sniper.ecom_scraper import EcomScraper
    s = EcomScraper()
    s.run(keywords=["boutique chaussures en ligne"], max_domains=200)
"""

import asyncio
import concurrent.futures
import logging
import os
import sys
import threading
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ─── Mots-clés e-commerce par catégorie ───────────────────────────────────────

DEFAULT_KEYWORDS = [
    # Mode / vêtements / accessoires
    "boutique vetements femme en ligne",
    "acheter chaussures femme pas cher",
    "bijoux fantaisie boutique en ligne",
    "maroquinerie sac boutique en ligne",
    # Beauté / cosmétiques
    "cosmetiques naturels boutique en ligne",
    "parfum pas cher boutique en ligne",
    # Maison / décoration
    "decoration interieur boutique en ligne",
    "luminaire design boutique en ligne",
    # Sport / outdoor
    "equipement sport boutique en ligne",
    "velo electrique boutique en ligne",
    # High-tech
    "accessoires smartphone boutique en ligne",
    "gaming accessoires boutique en ligne",
    # Santé / bien-être
    "complements alimentaires boutique en ligne",
    "materiel musculation boutique en ligne",
    # Enfant / bébé
    "jouets enfants boutique en ligne",
    "vetements bebe boutique en ligne",
    # Alimentation / épicerie fine
    "epicerie fine produits boutique en ligne",
    "the cafe boutique en ligne",
    # Animaux / jardinage
    "accessoires chien chat boutique en ligne",
    "jardinerie boutique en ligne",
]

# Domaines à ignorer (plateformes + grands sites + réseaux)
_BLACKLIST = {
    "wixsite.com", "wix.com", "squarespace.com", "weebly.com",
    "jimdo.com", "myshopify.com", "webflow.io",
    "facebook.com", "instagram.com", "linkedin.com", "twitter.com",
    "youtube.com", "tiktok.com", "pinterest.com",
    "google.com", "google.fr",
    "amazon.fr", "amazon.com", "ebay.fr", "leboncoin.fr",
    "cdiscount.com", "fnac.com", "darty.com", "zalando.fr",
    "wikipedia.org", "pages.google.com",
    "etsy.com", "veepee.fr", "vente-privee.com",
}

# CMS no-code = pas de budget prestataire
_AUTOGEREE_CMS = {
    "Wix", "Squarespace", "Weebly", "Jimdo", "Webflow",
    "Blogger", "Tumblr", "GoDaddy Website Builder",
    "Strikingly", "Carrd", "Notion", "Site123",
}

# Pages organiques par mot-clé (5 pages)
_ORGANIC_PAGES_PER_KW = 5


# ─── État partagé (pollable par le dashboard) ─────────────────────────────────

_state_lock = threading.Lock()

_state: Dict = {
    "running":       False,
    "phase":         None,
    "total_fetched": 0,
    "wap_done":      0,
    "accepted":      0,
    "rejected":      0,
    "errors":        0,
    "logs":          [],
    "started_at":    None,
    "ended_at":      None,
    "stop_requested": False,
}


def get_state() -> Dict:
    return dict(_state)


def reset_state() -> None:
    _state["running"] = False
    _state["phase"]   = None
    _state["stop_requested"] = False


def request_stop() -> None:
    """Demande l'arrêt propre du scraper."""
    _state["stop_requested"] = True
    _log("🛑 Arrêt demandé par l'utilisateur", level="warning")


def is_stop_requested() -> bool:
    """Vérifie si un arrêt a été demandé."""
    return _state.get("stop_requested", False)


def _log(msg: str, level: str = "info"):
    getattr(logger, level)(msg)
    _state["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    if len(_state["logs"]) > 50:
        _state["logs"].pop(0)


# ─── JS : extraction des résultats organiques ─────────────────────────────────

_JS_EXTRACT_ORGANIC = """
    () => {
        const urls = new Set();
        const search = document.querySelector('#search');
        if (!search) return [];
        search.querySelectorAll('a[href]').forEach(a => {
            const href = a.href || '';
            if (!href || href.includes('google.') || href.startsWith('#') || href.startsWith('javascript:'))
                return;
            // Exclure les blocs publicitaires
            if (a.closest('#tads') || a.closest('#bottomads') || a.closest('[data-text-ad]'))
                return;
            // Garder uniquement les liens principaux des résultats (div.g)
            if (!a.closest('.g') && !a.closest('[data-sokoban-container]'))
                return;
            // Exclure les liens cache, translate, etc.
            if (href.includes('webcache.google') || href.includes('translate.google'))
                return;
            urls.add(href);
        });
        return [...urls];
    }
"""

_JS_HAS_ORGANIC = """
    () => {
        const search = document.querySelector('#search');
        if (!search) return false;
        return search.querySelectorAll('h3').length > 0;
    }
"""


def _is_blacklisted(domain: str) -> bool:
    from urllib.parse import urlparse
    try:
        netloc = urlparse(domain).netloc.lower().lstrip("www.")
        return any(netloc == b or netloc.endswith("." + b) for b in _BLACKLIST)
    except Exception:
        return False


# ─── Phase 1A : Annonces Google (via ads_extractor) ───────────────────────────

def _fetch_ads_domains(keywords: List[str], country: str = "fr", max_per_kw: int = 30) -> List[Dict]:
    """
    Scrape les annonces Google pour les mots-clés e-commerce.
    Retourne [{"domaine": str, "mot_cle": str, "source": "ads"}, ...]
    """
    from scraper.sniper.ads_extractor import extract_ads
    raw = extract_ads(keywords, country=country, max_per_kw=max_per_kw, use_bing_fallback=False)
    results = []
    for item in raw:
        if not _is_blacklisted(item["domaine"]):
            results.append({
                "domaine":  item["domaine"],
                "mot_cle":  item["mot_cle"],
                "source":   "ads",
            })
    print(f"   [Ecom] Source A (Ads) : {len(results)} domaines annonceurs")
    return results


# ─── Phase 1B : Résultats organiques Google ───────────────────────────────────

async def _extract_organic_async(
    keywords: List[str],
    country: str = "fr",
    max_per_kw: int = 20,
    pages_per_kw: int = _ORGANIC_PAGES_PER_KW,
) -> List[Dict]:
    """
    Scrape les résultats organiques Google pour chaque mot-clé.
    Retourne [{"domaine": str, "mot_cle": str, "source": "organic"}, ...]
    """
    from scraper.sniper.ads_extractor import COUNTRY_PARAMS, _clean_url
    from core.browser import get_async_browser, _JS_IS_CAPTCHA, handle_captcha_async

    results: List[Dict] = []
    all_seen: set = set()

    try:
        browser = await get_async_browser()
    except Exception as e:
        logger.error(f"Chrome non disponible pour organique : {e}")
        return []

    params   = COUNTRY_PARAMS.get(country, COUNTRY_PARAMS["fr"])
    page = await browser.new_page()

    try:
        for kw in keywords:
            base_url = (
                f"https://www.{params['domain']}/search"
                f"?q={kw}&gl={params['gl']}&hl={params['hl']}&num=10"
            )
            found_kw = 0

            for page_idx in range(pages_per_kw):
                if found_kw >= max_per_kw:
                    break

                start = page_idx * 10
                url   = base_url if page_idx == 0 else f"{base_url}&start={start}"

                try:
                    from core.browser import wait_for_captcha_clear
                    await wait_for_captcha_clear()
                    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                    await page.wait_for_timeout(1500)
                    await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(800)
                except Exception as e:
                    logger.warning(f"Organique '{kw}' p{page_idx+1} navigation : {e}")
                    break

                if await page.evaluate(_JS_IS_CAPTCHA):
                    logger.warning(f"Organique '{kw}' — captcha détecté, mise en pause...")
                    page = await handle_captcha_async(page, label=f"Google Organique — {kw}")
                    
                    # Après résolution, on doit recharger l'URL pour s'assurer que les résultats s'affichent
                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                        await page.wait_for_timeout(1500)
                    except Exception:
                        break

                    # Si toujours bloqué après tentative de reprise, on passe au mot-clé suivant
                    if await page.evaluate(_JS_IS_CAPTCHA):
                        logger.warning(f"Organique '{kw}' — toujours bloqué après reprise, mot-clé ignoré")
                        break

                has_organic = await page.evaluate(_JS_HAS_ORGANIC)
                if not has_organic and page_idx > 0:
                    break

                raw_urls: List[str] = await page.evaluate(_JS_EXTRACT_ORGANIC) or []
                new_this_page = 0
                for href in raw_urls:
                    domain = _clean_url(href)
                    if not domain or domain in all_seen or _is_blacklisted(domain):
                        continue
                    all_seen.add(domain)
                    results.append({
                        "domaine": domain,
                        "mot_cle": kw,
                        "source":  "organic",
                    })
                    found_kw    += 1
                    new_this_page += 1

                print(
                    f"   [Ecom] Organique '{kw}' p{page_idx+1} -> "
                    f"{len(raw_urls)} liens | {new_this_page} nouveaux"
                )

                if new_this_page == 0:
                    print(f"   [Ecom] Aucun nouveau lead organique sur la page {page_idx+1}, arrêt de la pagination.")
                    logger.info(f"Organique '{kw}' — fin des résultats (aucun nouveau lead sur la page)")
                    break

                if page_idx < pages_per_kw - 1:
                    await asyncio.sleep(2)

            await asyncio.sleep(5)

    finally:
        # Fermer l'onglet seulement — NE PAS fermer la connexion CDP (profil Chrome).
        try:
            await page.close()
        except Exception:
            pass

    print(f"   [Ecom] Source B (Organique) : {len(results)} domaines")
    return results


def _fetch_organic_domains(keywords: List[str], country: str = "fr") -> List[Dict]:
    """Wrapper synchrone pour _extract_organic_async."""
    return asyncio.run(_extract_organic_async(keywords, country))


# ─── Phase 2 : Wappalyzer ─────────────────────────────────────────────────────

def _run_wappalyzer(site_web: str) -> dict:
    try:
        from scraper.sniper.wappalyzer_runner import analyze
        return analyze(site_web, timeout=30)
    except Exception as e:
        logger.debug(f"Wappalyzer {site_web} : {e}")
        return {"cms": None, "cdn": None, "ecommerce": None, "server": None,
                "technologies": [], "error": str(e)}


# ─── Phase 3 : PageSpeed ──────────────────────────────────────────────────────

def _run_pagespeed(site_web: str) -> dict:
    try:
        from auditeur.agents.web_analyzer import run_pagespeed
        return run_pagespeed(site_web, "mobile") or {}
    except Exception as e:
        logger.debug(f"PageSpeed {site_web} : {e}")
        return {}


# ─── Phase 4 + 5 : Scoring → DB ──────────────────────────────────────────────

def _score_and_store(item: dict, wap: dict, pagespeed: dict, campaign_id: int = None) -> bool:
    """
    Applique le scoring et insère le lead qualifié en base.
    Retourne True si accepté, False si rejeté.
    item = {"domaine": str, "mot_cle": str, "source": "ads"|"organic"}
    """
    from scraper.sniper.scoring import score_lead, build_donnees_audit
    from database import insert_lead, get_conn

    result = score_lead(pagespeed, wap, source="ecom")
    if result is None:
        tag, niveau, reason = "rejete", 0, "Site performant ou pas d'urgence"
        statut = "rejete"
    else:
        tag, niveau, reason = result
        statut = "en_attente"

    donnees = build_donnees_audit(pagespeed, wap, tag, niveau, reason, enriched={
        "ecom_source": item.get("source"),  # 'ads' ou 'organic'
    })

    # Déduplication par domaine
    domain = item["domaine"]
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM leads_bruts WHERE site_web LIKE ? AND source='ecom'",
            (f"%{domain.replace('https://', '').replace('http://', '')}%",)
        ).fetchone()
        if existing:
            logger.debug(f"Ecom — {domain} déjà présent, ignoré")
            return False

    lead_id = insert_lead({
        "campaign_id":    campaign_id,
        "nom":            "",
        "adresse":        "",
        "ville":          "",
        "site_web":       domain,
        "telephone":      "",
        "email":          "",
        "mot_cle":        item.get("mot_cle", ""),
        "category":       item.get("mot_cle", "E-commerce"),
        "source":         "ecom",
        "tag_urgence":    tag,
        "niveau_urgence": niveau,
        "donnees_audit":  donnees,
        "statut":         statut,
    })

    if lead_id:
        cms = wap.get("cms") or wap.get("ecommerce") or "?"
        _log(f"  +  {domain} — {tag} niv.{niveau} | {cms} | {reason[:60]}")
        return statut == "en_attente"

    return False


# ─── Orchestrateur ────────────────────────────────────────────────────────────

class EcomScraper:
    """
    Scraper Source 2 — e-commerçants via Google Search (ads + organic).

    Usage :
        s = EcomScraper()
        s.run(keywords=["boutique chaussures en ligne"], max_domains=200)
    """

    def run(
        self,
        keywords:    Optional[List[str]] = None,
        country:     str = "fr",
        city:        str = "",
        max_domains: int = 300,
        max_leads:   int = 50,
        parallel:    int = 3,
        campaign_name: Optional[str] = None,
        skip_ads:    bool = False,
        skip_organic: bool = False,
        min_leads:   int = 0,   # Quota minimum — déclenche la rotation de villes
    ) -> Dict:
        if _state["running"]:
            return {"error": "EcomScraper déjà en cours"}

        _state.update({
            "running": True, "phase": "fetch",
            "total_fetched": 0, "wap_done": 0,
            "accepted": 0, "rejected": 0, "errors": 0,
            "stop_requested": False,  # Réinitialisation cruciale
            "logs": [], "started_at": datetime.now().isoformat(), "ended_at": None,
        })

        if keywords is None:
            keywords = DEFAULT_KEYWORDS

        try:
            from database import insert_campaign
            if not campaign_name:
                campaign_name = f"Sniper Ecom — {datetime.now().strftime('%d/%m %H:%M')}"
            campaign_id = insert_campaign(campaign_name, "ecom", country)
            _log(f"Campagne créée : #{campaign_id} — {campaign_name}")

            # ── Rotation de villes — état initial ────────────────────────────
            from core.city_rotator import CityRotator
            rotator           = CityRotator(country=country, keywords=keywords, source="ecom")
            original_keywords = list(keywords)
            if city:
                current_keywords = [f"{kw} {city}" if city.lower() not in kw.lower() else kw for kw in keywords]
                rotator._used.add(city)
                rotation_pass     = 0
            else:
                current_keywords = rotator.next_batch_multi(original_keywords, batch_size=3)
                rotator.mark_used(current_keywords)
                rotation_pass     = 1

            # ── Boucle Phase 1 → enrichissement (+ rotation villes) ──────────
            while True:
                # — Phase 1 : Collecte des domaines ───────────────────────────
                _state["phase"] = "fetch"
                prefix = f"[Rotation #{rotation_pass}] " if rotation_pass else ""
                _log(f"Phase 1 {prefix}— Google Search ({len(current_keywords)} mots-clés, pays={country})")

                all_items: List[Dict] = []
                seen_domains: set = set()

                def _add_items(items: List[Dict]):
                    for item in items:
                        d = item["domaine"]
                        if d not in seen_domains:
                            seen_domains.add(d)
                            all_items.append(item)

                if not skip_ads:
                    _log("  Source A — annonces Google")
                    ads_items = _fetch_ads_domains(current_keywords, country=country, max_per_kw=30)
                    _add_items(ads_items)
                    _log(f"    {len(ads_items)} domaines annonceurs")

                if not skip_organic:
                    _log("  Source B — résultats organiques Google")
                    organic_items = _fetch_organic_domains(current_keywords, country=country)
                    _add_items(organic_items)
                    _log(f"    {len(organic_items)} domaines organiques")

                all_items = all_items[:max_domains]
                _state["total_fetched"] += len(all_items)
                _log(f"Passe #{rotation_pass} : {len(all_items)} domaines à analyser")

                if all_items:
                    # — Phase 2+3+4+5 : Wap → PageSpeed → Scoring → DB ────────
                    _state["phase"] = "enrichissement"
                    _log(f"Phase 2 — Wappalyzer + scoring ({parallel} threads, max {max_leads} leads)")

                    def _process(item: dict) -> bool:
                        domain = item["domaine"]
                        try:
                            wap = _run_wappalyzer(domain)
                            with _state_lock:
                                _state["wap_done"] += 1

                            cms = wap.get("cms") or wap.get("ecommerce")
                            if cms and cms in _AUTOGEREE_CMS:
                                print(f"   [Ecom] REJET {domain} — CMS no-code : {cms}")
                                return False

                            pagespeed = _run_pagespeed(domain)
                            score = pagespeed.get("mobile_score")
                            cdn = wap.get("cdn")
                            print(
                                f"   [Ecom] {domain} "
                                f"| CMS={cms or '?'} CDN={cdn or 'aucun'} "
                                f"| score={int(score) if score else '?'}"
                            )
                            return _score_and_store(item, wap, pagespeed, campaign_id=campaign_id)

                        except Exception as e:
                            logger.error(f"Ecom — _process {item.get('domaine')} : {e}")
                            with _state_lock:
                                _state["errors"] += 1
                            return False
                        finally:
                            try:
                                from core.browser import cleanup_sync_thread
                                cleanup_sync_thread()
                            except Exception:
                                pass

                    with concurrent.futures.ThreadPoolExecutor(max_workers=parallel) as executor:
                        futures = {executor.submit(_process, item): item for item in all_items}
                        for future in concurrent.futures.as_completed(futures):
                            with _state_lock:
                                quota_atteint = _state["accepted"] >= max_leads
                            if quota_atteint:
                                executor.shutdown(wait=False, cancel_futures=True)
                                break
                            try:
                                accepted = future.result()
                                with _state_lock:
                                    if accepted:
                                        _state["accepted"] += 1
                                    else:
                                        _state["rejected"] += 1
                            except Exception as e:
                                with _state_lock:
                                    _state["errors"] += 1
                                logger.error(f"Ecom — future error : {e}")

                # — Vérification quota + rotation ────────────────────────────
                accepted_total = _state["accepted"]
                quota_cible = min_leads if min_leads > 0 else max_leads
                if accepted_total < quota_cible and rotator.has_more():
                    rotation_pass += 1
                    current_keywords = rotator.next_batch_multi(original_keywords, batch_size=3)
                    rotator.mark_used(current_keywords)
                    _log(
                        f"  [{accepted_total}/{quota_cible} leads] Rotation #{rotation_pass} —"
                        f" {len(current_keywords)} nouvelles variantes"
                    )
                    continue
                break   # quota atteint ou plus de villes

            _log(
                f"EcomScraper terminé — "
                f"{_state['accepted']} leads qualifiés, "
                f"{_state['rejected']} rejetés, "
                f"{_state['errors']} erreurs"
                + (f" [rotation x{rotation_pass}]" if rotation_pass else "")
            )
            return {
                "accepted":    _state["accepted"],
                "rejected":    _state["rejected"],
                "errors":      _state["errors"],
                "campaign_id": campaign_id,
            }

        except Exception as e:
            logger.error(f"EcomScraper erreur critique : {e}")
            _log(f"ERREUR CRITIQUE : {e}", "error")
            return {"error": str(e)}

        finally:
            _state["running"]  = False
            _state["phase"]    = "done"
            _state["ended_at"] = datetime.now().isoformat()
