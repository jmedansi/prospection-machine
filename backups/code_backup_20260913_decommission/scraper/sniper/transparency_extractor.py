# -*- coding: utf-8 -*-
"""
scraper/sniper/transparency_extractor.py — Google Ads Transparency Center

Stratégie :
  1. Playwright navigue sur adstransparency.google.com
  2. Tape le mot-clé dans la barre de recherche (interaction réelle)
  3. Intercepte les réponses réseau protobuf → extrait les URLs lisibles en ASCII
  4. Scrape les liens /advertiser/AR... dans le DOM
  5. Pour chaque annonceur, visite sa page et récupère le site web

Pas d'appel RPC direct (protobuf binaire requis, non implémentable simplement).
"""

import asyncio
import logging
import re
from typing import List, Dict, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

BASE_URL = "https://adstransparency.google.com"

def _is_stop_requested() -> bool:
    try:
        from scraper.sniper.transparency_pipeline import is_stop_requested
        return is_stop_requested()
    except Exception:
        return False

BLACKLIST = {
    "wixsite.com", "wix.com", "squarespace.com", "weebly.com",
    "jimdo.com", "myshopify.com", "webflow.io",
    "facebook.com", "instagram.com", "linkedin.com", "twitter.com",
    "youtube.com", "tiktok.com", "pinterest.com",
    "google.com", "google.fr", "google.ch", "google.be",
    "amazon.fr", "amazon.com", "ebay.fr", "leboncoin.fr",
    "wikipedia.org", "pages.google.com", "adstransparency.google.com",
}

REGION_MAP = {
    "FR": "FR", "CH": "CH", "BE": "BE", "LU": "LU",
    "DE": "DE", "ES": "ES", "IT": "IT", "US": "US",
}


def _clean_domain(url: str) -> Optional[str]:
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        if not netloc or "." not in netloc or len(netloc) < 4:
            return None
        if any(netloc == b or netloc.endswith("." + b) for b in BLACKLIST):
            return None
        return f"https://{parsed.netloc.lower()}"
    except Exception:
        return None


def _extract_urls_from_bytes(data: bytes) -> List[str]:
    """Extrait les URLs lisibles depuis une réponse protobuf binaire."""
    try:
        text = data.decode("utf-8", errors="ignore")
    except Exception:
        text = ""
    # Les URLs sont stockées en clair dans le protobuf
    urls = re.findall(r'https?://[a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,}(?:/[^\s\x00-\x1f"\'<>]*)?', text)
    
    noisy_domains = ['google', 'gstatic', 'youtube', 'doubleclick', 'fonts.', 'googletag', 'facebook', 'instagram', 'twitter', 'linkedin', 'w3.org', 'schema.org']
    filtered = []
    for u in urls:
        if len(u) > 10 and not any(noise in u.lower() for noise in noisy_domains):
            filtered.append(u)
    return filtered


async def _search_and_collect(page, keyword: str, region: str, max_results: int) -> List[Dict]:
    """
    Navigue sur la page Transparency, tape le mot-clé dans la barre de recherche,
    intercepte les réponses réseau et scrape les liens annonceurs.
    """
    advertiser_links: set = set()
    captured_domains: List[str] = []

    # ── Interception réseau : capturer les réponses protobuf ──────────────────
    async def on_response(response):
        url = response.url
        if "rpc" in url or "GetAdvertiser" in url or "tfaar" in url.lower():
            try:
                body = await response.body()
                urls = _extract_urls_from_bytes(body)
                captured_domains.extend(urls)
            except Exception:
                pass

    page.on("response", on_response)

    try:
        # Navigation sur la page principale avec le filtre région
        await page.goto(
            f"{BASE_URL}/?region={region}&hl=fr",
            wait_until="domcontentloaded",
            timeout=30_000
        )
        
        try:
            from core.browser import handle_captcha_async
            page = await handle_captcha_async(page, label="Google Ads Transparency")
        except Exception as e:
            logger.warning(f"Captcha handler failed or not imported: {e}")

        # Attente dynamique pour la stabilisation initiale
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

        # Chercher la barre de recherche de manière plus robuste (Locator Playwright)
        search_input = None
        try:
            locators = page.locator('input[type="search"], input[aria-label*="Search"], input[aria-label*="search"], input[placeholder*="Search"], input[placeholder*="Recherch"], input')
            if await locators.count() > 0:
                for i in range(await locators.count()):
                    el = locators.nth(i)
                    if await el.is_visible():
                        search_input = el
                        break
        except Exception as e:
            logger.warning(f"Erreur locator search: {e}")

        if search_input:
            logger.info(f"Barre de recherche trouvée pour '{keyword}'")
            await search_input.click()
            await page.wait_for_timeout(500)
            await search_input.fill(keyword)
            await page.wait_for_timeout(500)
            await search_input.press("Enter")
            # Attente réseau dynamique au lieu d'un délai strict
            try:
                await page.wait_for_load_state("networkidle", timeout=10_000)
            except Exception:
                await page.wait_for_timeout(5000)
        else:
            # Fallback : URL directe avec paramètre query
            logger.warning(f"Barre de recherche non trouvée — URL directe")
            await page.goto(
                f"{BASE_URL}/?region={region}&hl=fr&query={keyword.replace(' ', '+')}",
                wait_until="domcontentloaded",
                timeout=25_000
            )
            try:
                await page.wait_for_load_state("networkidle", timeout=10_000)
            except Exception:
                await page.wait_for_timeout(5000)

        # Scroller pour déclencher le chargement lazy
        for _ in range(3):
            await page.evaluate("window.scrollBy(0, 600)")
            await page.wait_for_timeout(1000)

        # ── Scraping DOM : liens /advertiser/AR... ────────────────────────────
        links = await page.evaluate("""
        () => {
            const found = new Set();
            // Liens directs vers des pages annonceurs
            document.querySelectorAll('a[href]').forEach(a => {
                const h = a.getAttribute('href') || '';
                if (h.includes('/advertiser/')) found.add(h);
            });
            // Shadow DOM : certains composants Angular encapsulent leurs éléments
            document.querySelectorAll('*').forEach(el => {
                if (el.shadowRoot) {
                    el.shadowRoot.querySelectorAll('a[href]').forEach(a => {
                        const h = a.getAttribute('href') || '';
                        if (h.includes('/advertiser/')) found.add(h);
                    });
                }
            });
            return [...found];
        }
        """) or []

        for link in links:
            # Normaliser : /advertiser/AR... ou https://adstransparency.google.com/advertiser/AR...
            match = re.search(r'/advertiser/(AR[^/?&\s]+)', link)
            if match:
                advertiser_links.add(match.group(1))

        logger.info(
            f"'{keyword}' — {len(advertiser_links)} annonceurs DOM, "
            f"{len(captured_domains)} domaines protobuf"
        )

    except Exception as e:
        logger.error(f"_search_and_collect erreur pour '{keyword}': {e}")
    finally:
        page.remove_listener("response", on_response)

    # Construire la liste de résultats
    results = []

    # Priorité 1 : annonceurs avec ID (on ira chercher leur site)
    for adv_id in list(advertiser_links)[:max_results]:
        results.append({
            "advertiser_id": adv_id,
            "name": "",
            "domaine": None,
            "keyword": keyword,
            "region": region,
        })

    # Priorité 2 : domaines capturés depuis protobuf (si pas assez d'IDs)
    seen_domains = set()
    for url in captured_domains:
        if len(results) >= max_results:
            break
        domain = _clean_domain(url)
        if domain and domain not in seen_domains:
            seen_domains.add(domain)
            # Vérifier qu'on n'a pas déjà ce domaine
            results.append({
                "advertiser_id": "",
                "name": "",
                "domaine": domain,
                "keyword": keyword,
                "region": region,
            })

    return results[:max_results]


async def _resolve_advertiser_domain(page, advertiser_id: str) -> Optional[str]:
    """
    Visite la page d'un annonceur et récupère son site web.
    Intercepte aussi les réponses réseau sur cette page.
    """
    if not advertiser_id:
        return None

    captured_urls = []

    async def on_response(response):
        url = response.url
        if "rpc" in url or advertiser_id in url:
            try:
                body = await response.body()
                urls = _extract_urls_from_bytes(body)
                captured_urls.extend(urls)
            except Exception:
                pass

    page.on("response", on_response)

    try:
        await page.goto(
            f"{BASE_URL}/advertiser/{advertiser_id}?hl=fr",
            wait_until="domcontentloaded",
            timeout=20_000
        )
        await page.wait_for_timeout(3000)

        # Chercher le site web dans le DOM
        domain_from_dom = await page.evaluate("""
        () => {
            // Chercher des liens externes dans la page de l'annonceur
            const links = [];
            document.querySelectorAll('a[href]').forEach(a => {
                const h = a.href || '';
                if (h.startsWith('http') &&
                    !h.includes('google') &&
                    !h.includes('adstransparency') &&
                    !h.startsWith('#') &&
                    !h.includes('javascript')) {
                    links.push(h);
                }
            });
            // Texte affiché comme URL de l'annonceur
            document.querySelectorAll('[class*="url"], [class*="domain"], [class*="website"]').forEach(el => {
                const t = el.textContent.trim();
                if (t && t.includes('.') && !t.includes(' ') && t.length > 4) links.push(t);
            });
            return [...new Set(links)].slice(0, 5);
        }
        """) or []

        for link in domain_from_dom:
            d = _clean_domain(link)
            if d:
                return d

        # Fallback : domaines capturés dans le réseau
        for url in captured_urls:
            d = _clean_domain(url)
            if d:
                return d

        # Dernier recours : extraire depuis les créatifs d'annonces (URL affichée)
        ad_display_urls = await page.evaluate(r"""
        () => {
            const urls = [];
            // Les annonces affichent souvent l'URL du site en petit texte vert
            const all = document.querySelectorAll('*');
            all.forEach(el => {
                if (el.children.length === 0) {  // noeuds texte
                    const t = el.textContent.trim();
                    if (/^[a-zA-Z0-9\-\.]+\.[a-z]{2,}(\/[^\s]*)?$/.test(t) && t.length > 5 && t.length < 60) {
                        urls.push(t);
                    }
                }
            });
            return [...new Set(urls)].slice(0, 10);
        }
        """) or []

        for display_url in ad_display_urls:
            d = _clean_domain(display_url if display_url.startswith("http") else f"https://{display_url}")
            if d:
                return d

    except Exception as e:
        logger.warning(f"_resolve_advertiser_domain({advertiser_id}): {e}")
    finally:
        page.remove_listener("response", on_response)

    return None


async def extract_transparency_async(
    keywords: List[str],
    country: str = "FR",
    max_per_kw: int = 20,
) -> List[Dict]:
    """
    Extrait les annonceurs depuis Google Ads Transparency Center.

    Returns:
        [{"domaine": str, "mot_cle": str, "pays": str}, ...]
    """
    from core.browser import get_async_browser

    region = REGION_MAP.get(country.upper(), "FR")
    results: List[Dict] = []
    all_seen_domains: set = set()

    browser = await get_async_browser()
    page = await browser.new_page()
    try:
        for kw in keywords:
            if _is_stop_requested():
                logger.info("[Transparency] Arrêt d'urgence demandé.")
                break
            logger.info(f"[Transparency] Recherche : '{kw}' (région={region})")

            try:
                candidates = await _search_and_collect(page, kw, region, max_per_kw)
                logger.info(f"  → {len(candidates)} candidats pour '{kw}'")

                for cand in candidates:
                    if _is_stop_requested():
                        break
                    domain = cand.get("domaine")
                    if not domain and cand.get("advertiser_id"):
                        domain = await _resolve_advertiser_domain(page, cand["advertiser_id"])
                        await asyncio.sleep(1)

                    if domain and domain not in all_seen_domains:
                        all_seen_domains.add(domain)
                        results.append({
                            "domaine":         domain,
                            "mot_cle":         kw,
                            "pays":            country,
                            "advertiser_name": cand.get("name", ""),
                            "advertiser_id":   cand.get("advertiser_id", ""),
                            "source":          "transparency",
                        })
                        logger.info(f"  ✓ {domain}")

            except Exception as e:
                logger.error(f"Erreur pour '{kw}': {e}")

            await asyncio.sleep(3)

    finally:
        # Fermer l'onglet seulement — NE PAS fermer la connexion CDP (profil Chrome).
        try:
            await page.close()
        except Exception:
            pass

    logger.info(f"[Transparency] Total : {len(results)} annonceurs")
    return results


def extract_transparency_ads(
    keywords: List[str],
    country: str = "FR",
    max_per_kw: int = 20,
) -> List[Dict]:
    """Wrapper synchrone."""
    return asyncio.run(extract_transparency_async(keywords, country, max_per_kw))
