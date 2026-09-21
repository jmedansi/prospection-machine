# -*- coding: utf-8 -*-
"""
scraper/sniper/fb_ads_browser_extractor.py — Meta Ad Library Browser Scraper

Remplace l'API officielle par une extraction via navigateur (Playwright).
Avantage : Pas de token requis.
Récupère directement la Landing Page (URL finale) de la publicité.
"""

import asyncio
import logging
import traceback
from typing import Dict, List
from urllib.parse import urlparse, quote_plus

logger = logging.getLogger(__name__)

# Domaines à exclure (réseaux sociaux, bio-links, etc.)
_SOCIAL_DOMAINS = {
    "facebook.com", "instagram.com", "linkedin.com", "twitter.com",
    "tiktok.com", "youtube.com", "linktr.ee", "linktree.com",
    "bio.link", "beacons.ai", "carrd.co", "wa.me", "m.me", "fb.me",
}


def _is_social_url(url: str) -> bool:
    try:
        netloc = urlparse(url).netloc.lower().lstrip("www.")
        return any(netloc == d or netloc.endswith("." + d) for d in _SOCIAL_DOMAINS)
    except Exception:
        return False


async def extract_fb_ads_browser(
    search_terms: List[str],
    country: str = "FR",
    max_ads_per_kw: int = 20,
) -> List[Dict]:
    """
    Extrait les annonceurs et leurs landing pages via le navigateur CDP.
    Retourne une liste vide (et logge l'erreur) si le navigateur est indisponible.
    """
    from core.browser import get_async_browser

    results         = []
    seen_landing    = set()
    page            = None   # guard NameError dans finally

    try:
        browser = await get_async_browser()
    except Exception as e:
        logger.error(f"[FB Extractor] Impossible de se connecter au navigateur: {type(e).__name__}: {e}")
        logger.debug(traceback.format_exc())
        return []

    # Onglet dans le profil par défaut (pas incognito)
    try:
        page = await browser.new_page()
    except Exception as e:
        logger.error(f"[FB Extractor] Impossible d'ouvrir un onglet: {e}")
        return []

    try:
        for kw in search_terms:
            # URL encodée proprement (gère accents, espaces, guillemets)
            kw_encoded = quote_plus(kw)
            url = (
                f"https://www.facebook.com/ads/library/"
                f"?active_status=active&ad_type=all&country={country}"
                f"&q={kw_encoded}&sort_data[direction]=desc"
                f"&sort_data[mode]=relevancy_monthly_grouped"
                f"&search_type=keyword_unordered"
            )

            logger.info(f"[FB Extractor] Scan '{kw}' (pays={country})")

            # Navigation — domcontentloaded est plus fiable que networkidle sur Meta
            success = False
            for attempt in range(2):
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                    success = True
                    break
                except Exception as e:
                    logger.warning(f"[FB Extractor] Tentative {attempt + 1}/2 échouée pour '{kw}': {type(e).__name__}")
                    if attempt == 0:
                        await page.wait_for_timeout(3_000)

            if not success:
                logger.error(f"[FB Extractor] Impossible de charger Ad Library pour '{kw}' — mots-clé ignoré")
                continue

            # Attente hydratation React + scroll pour lazy-loading
            await page.wait_for_timeout(6_000)
            for i in range(4):
                await page.evaluate("window.scrollBy(0, 1500)")
                await page.wait_for_timeout(1_500)
                if i % 2 == 0:
                    await page.evaluate("window.scrollBy(0, -300)")
                    await page.wait_for_timeout(500)

            # Extraction JS — robuste, basée sur les CTAs externes
            try:
                ads_data = await page.evaluate(r'''() => {
                    const results = [];
                    const seenContainers = new Set();

                    // Stratégie 1 : liens CTA externes (l.facebook.com ou href^=http hors FB)
                    const ctas = document.querySelectorAll(
                        'a[href*="l.facebook.com/l.php"], a[href^="http"]:not([href*="facebook.com"]):not([href*="instagram.com"])'
                    );

                    const adCards = [];
                    if (ctas.length > 0) {
                        for (const cta of ctas) {
                            const card = cta.closest('div[style*="border"], div[class*="xh8yej3"], div.x1yztbdb');
                            if (card) adCards.push({ card, cta });
                        }
                    } else {
                        // Fallback : cartes génériques
                        const cards = document.querySelectorAll('div[class*="xh8yej3"], div.x1yztbdb, div[style*="border-radius: 8px"]');
                        cards.forEach(c => adCards.push({ card: c, cta: null }));
                    }

                    for (const item of adCards) {
                        const { card, cta } = item;
                        if (seenContainers.has(card)) continue;
                        seenContainers.add(card);

                        // Nom de la page
                        let pageName = "";
                        const pageLink = card.querySelector('a[href*="view_all_page_id="]');
                        if (pageLink) {
                            const match = pageLink.href.match(/view_all_page_id=(\d+)/);
                            const pageId = match ? match[1] : "";
                            pageName = (pageLink.innerText || pageLink.textContent || "").trim();
                            // Corps de l'annonce
                            let adBody = "";
                            const textEls = Array.from(card.querySelectorAll('div[dir="auto"], span[dir="auto"]'))
                                .filter(el => {
                                    const t = (el.innerText || el.textContent || "").trim();
                                    return t.length > 20 && !t.includes(pageName);
                                });
                            if (textEls.length > 0) adBody = (textEls[0].innerText || textEls[0].textContent || "").trim();

                            // Date
                            let adStart = "";
                            const timeEl = Array.from(card.querySelectorAll('span')).find(el => (el.innerText || "").includes("diffusée le"));
                            if (timeEl) adStart = (timeEl.innerText || "").trim();

                            // Landing page
                            let landingPage = "";
                            const ctaLink = cta || card.querySelector('a[href*="l.facebook.com/l.php"], a[href^="http"]:not([href*="facebook.com"])');
                            if (ctaLink) {
                                const href = ctaLink.getAttribute("href") || "";
                                if (href.includes("l.facebook.com/l.php")) {
                                    try {
                                        const u = new URL(href).searchParams.get("u");
                                        if (u) landingPage = decodeURIComponent(u).split("?")[0];
                                    } catch(e) {}
                                } else {
                                    landingPage = href.split("?")[0];
                                }
                            }

                            if (landingPage) {
                                results.push({ pageName, pageId, adBody: adBody.slice(0, 300), landingPage, adStart });
                            }
                        }
                    }
                    return results;
                }''')
            except Exception as e:
                logger.warning(f"[FB Extractor] Erreur JS evaluate pour '{kw}': {type(e).__name__}: {e}")
                continue

            logger.info(f"[FB Extractor] '{kw}' → {len(ads_data)} publicité(s) dans le DOM")

            found_for_kw = 0
            for ad in ads_data:
                if found_for_kw >= max_ads_per_kw:
                    break
                try:
                    lp   = ad.get("landingPage", "").strip()
                    name = ad.get("pageName", "Annonceur inconnu").strip() or "Annonceur inconnu"

                    if not lp or lp in seen_landing or _is_social_url(lp):
                        continue

                    seen_landing.add(lp)
                    results.append({
                        "page_id":   ad.get("pageId", ""),
                        "page_name": name,
                        "site_web":  lp,
                        "has_site":  True,
                        "category":  "Annonceur Meta",
                        "fan_count": 0,
                        "ad_body":   ad.get("adBody", ""),
                        "ad_start":  ad.get("adStart", ""),
                        "mot_cle":   kw,
                        "pays":      country,
                    })
                    found_for_kw += 1
                    logger.debug(f"[FB Extractor]   ✓ {name} → {lp}")

                except Exception as e:
                    logger.warning(f"[FB Extractor] Erreur parsing bloc: {e}")

            logger.info(f"[FB Extractor] '{kw}' → {found_for_kw} annonceur(s) unique(s) retenus")

    finally:
        # Fermer l'onglet seulement — NE PAS fermer la connexion CDP (profil Chrome).
        if page is not None:
            try:
                await page.close()
            except Exception:
                pass

    logger.info(f"[FB Extractor] Total : {len(results)} annonceurs Meta extraits")
    return results


def extract_fb_ads(search_terms: List[str], country: str = "FR", max_pages: int = 5) -> List[Dict]:
    """
    Wrapper synchrone — crée sa propre event loop pour éviter les conflits avec Flask.
    max_pages est converti en limite de pubs par mot-clé (×10).
    """
    limit = max_pages * 10

    # Nouvelle loop dédiée à ce thread (compatible même si Flask a sa propre loop)
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(extract_fb_ads_browser(search_terms, country, limit))
    except Exception as e:
        logger.error(f"[FB Extractor] Erreur dans la loop asyncio: {e}")
        return []
    finally:
        try:
            loop.close()
        except Exception:
            pass
