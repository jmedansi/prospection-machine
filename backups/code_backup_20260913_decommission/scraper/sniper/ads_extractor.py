# -*- coding: utf-8 -*-
"""
scraper/sniper/ads_extractor.py — Phase 1 : Extraction des annonceurs Google/Bing

Stratégie :
  1. Patchright (anti-détection) charge une page de résultats Google ou Bing
  2. On isole les blocs "Sponsored" / "Commandité" et on extrait les domaines
  3. On nettoie les URLs de tracking (gclid, utm_*, etc.)
  4. On rejette les plateformes blacklistées (Wix, Facebook, etc.)

Usage direct :
    from scraper.sniper.ads_extractor import extract_ads
    leads = extract_ads(["Boutique vêtement sport", "Logiciel B2B Paris"], country="fr")
"""

import asyncio
import logging
import os
import random
import sys
from typing import List, Dict, Optional
from urllib.parse import urlparse, parse_qs

# Ajout du ROOT au sys.path pour permettre l'import de 'core'
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

logger = logging.getLogger(__name__)

# ─── Paramètres pays ─────────────────────────────────────────────────────────

COUNTRY_PARAMS = {
    "fr": {"gl": "fr", "hl": "fr", "domain": "google.fr"},
    "ch": {"gl": "ch", "hl": "fr", "domain": "google.ch"},
    "be": {"gl": "be", "hl": "fr", "domain": "google.be"},
    "lu": {"gl": "lu", "hl": "fr", "domain": "google.lu"},
}

# ─── Domaines à exclure (plateformes low-code, réseaux sociaux, agrégateurs) ─

BLACKLIST = {
    "wixsite.com", "wix.com", "squarespace.com", "weebly.com",
    "jimdo.com", "myshopify.com", "webflow.io",
    "facebook.com", "instagram.com", "linkedin.com", "twitter.com",
    "youtube.com", "tiktok.com", "pinterest.com",
    "google.com", "google.fr", "google.ch", "google.be",
    "amazon.fr", "amazon.com", "ebay.fr", "leboncoin.fr",
    "wikipedia.org", "pages.google.com",
}

# ─── Sélecteurs Google Ads (multi-stratégie, du plus au moins fiable) ────────

# Les annonces Google en 2024-2025 utilisent ces marqueurs :
# - data-text-ad="1" sur le container (le plus stable)
# - liens /aclk?... (redirect Google Ads)
# - <span> contenant "Commandité" ou "Sponsored" suivi d'un lien

_GOOGLE_AD_SELECTORS = [
    # Container principal des text ads
    '[data-text-ad] cite',
    '[data-text-ad] a[href]:not([href^="#"])',
    # Liens de redirect ads Google
    'a[href*="/aclk"]',
    # Blocs ads identifiés par leurs divs
    'div[id^="tads"] a[href]:not([href^="#"])',
    'div[id^="bottomads"] a[href]:not([href^="#"])',
]

_BING_AD_SELECTORS = [
    'li.b_ad a.b_restoreable',
    '.b_adSlug a',
    '#b_results .b_ad a[href]',
]


# ─── User-Agents récents pour rotation (évite le fingerprint) ────────────────

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
]

def _random_viewport() -> dict:
    """Viewport différent à chaque nouveau contexte pour éviter le fingerprint."""
    return {
        "width": random.randint(1700, 2100),
        "height": random.randint(900, 1200),
    }


# ─── Nettoyage d'URL ──────────────────────────────────────────────────────────

_TRACKING_PARAMS = {
    "gclid", "gclsrc", "gbraid", "wbraid",
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "msclkid", "_ga", "dclid",
}


def _clean_url(href: str) -> Optional[str]:
    """
    Extrait le domaine propre depuis une URL brute (y compris /aclk? redirects).
    Retourne None si l'URL est invalide ou blacklistée.
    """
    if not href or href.startswith("#") or href.startswith("javascript:"):
        return None

    # Ajouter le schéma si absent (cas data-dtld / cite qui retournent le domaine seul)
    if not href.startswith(("http://", "https://")) and not href.startswith("/"):
        href = "https://" + href

    # Déplier les redirects Google /url?q=... ou /aclk?adurl=...
    if "/aclk" in href or href.startswith("https://www.google.com/url"):
        parsed = urlparse(href)
        params = parse_qs(parsed.query)
        dest = (
            params.get("adurl", [None])[0]
            or params.get("q", [None])[0]
            or params.get("url", [None])[0]
        )
        if dest:
            href = dest
        else:
            return None

    try:
        parsed = urlparse(href)
        if not parsed.netloc or not parsed.scheme:
            return None

        # Reconstruire proprement : scheme + netloc seulement
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]

        # Vérifier blacklist
        if any(netloc == b or netloc.endswith("." + b) for b in BLACKLIST):
            return None

        # Doit avoir un TLD valide
        if "." not in netloc or len(netloc) < 4:
            return None

        return f"{parsed.scheme}://{netloc}"

    except Exception:
        return None


# ─── Extraction async ─────────────────────────────────────────────────────────

_JS_EXTRACT_ADS = """
    () => {
        const urls = new Set();

        // Tier 1 — data-pcu : URL finale directe, signal 100% publicitaire
        document.querySelectorAll('[data-pcu]').forEach(el => {
            const u = el.getAttribute('data-pcu') || '';
            if (u.startsWith('http') && !u.includes('google.')) urls.add(u);
        });

        // Tier 2 — data-dtld : URL affichée dans les nouvelles annonces responsive
        document.querySelectorAll('[data-dtld]').forEach(el => {
            const u = el.getAttribute('data-dtld') || '';
            if (u && !u.includes('google.') && u.includes('.')) {
                const scheme = u.startsWith('http') ? '' : 'https://';
                urls.add(scheme + u);
            }
        });

        // Tier 3 — /aclk : redirect Google Ads (signal le plus fiable, jamais sur résultats organiques)
        document.querySelectorAll('a[href*="/aclk"]').forEach(a => {
            if (a.href) urls.add(a.href);
        });

        // Tier 4 — [data-text-ad] : container des annonces texte Google
        document.querySelectorAll('[data-text-ad] a[href]').forEach(a => {
            if (a.href && !a.href.includes('google.') && !a.href.startsWith('#'))
                urls.add(a.href);
        });

        // Tier 5 — #tads / #bottomads : sections publicitaires (jamais de résultats Maps ici)
        ['#tads', '#bottomads'].forEach(sel => {
            const el = document.querySelector(sel);
            if (el) el.querySelectorAll('a[href]').forEach(a => {
                if (a.href && !a.href.includes('google.') && !a.href.startsWith('#'))
                    urls.add(a.href);
            });
        });

        // Tier 6 — cite dans les containers ad : URL visible sous le titre de l'annonce
        document.querySelectorAll('[data-text-ad] cite, #tads cite, #bottomads cite').forEach(cite => {
            const txt = cite.textContent.trim();
            if (txt && txt.includes('.') && !txt.includes('google.') && txt.length > 4) {
                urls.add('https://' + txt.split('/')[0].replace(/^https?:\\/\\//, ''));
            }
        });

        return [...urls];
    }
"""


_MAX_PAGES_SAFETY = 3  # plafond de sécurité — 3 pages max pour limiter les renderers Chrome
_KEYWORD_TIMEOUT = 120  # timeout global par mot-clé (secondes)

# Import hissé au module level (ne pas importer dans une boucle — dépendance circulaire silencieuse)
try:
    from scraper.sniper.pipeline import is_stop_requested as _is_stop_requested, request_stop as _request_stop
except ImportError:
    def _is_stop_requested() -> bool:
        return False
    def _request_stop() -> None:
        pass

from core.browser import _JS_IS_CAPTCHA, handle_captcha_async as _handle_captcha_page, patch_page


# ─── Détection blocage Google 403 ────────────────────────────────────────────

_BLOCK_SIGNATURES = [
    "does not have permission",
    "that's an error",
    "403. that",
    "error 403",
    "access denied",
    "our systems have detected unusual traffic",
]


async def _is_google_blocked(page) -> bool:
    """Retourne True si la page indique un blocage Google (403, traffic inhabituel)."""
    try:
        content = (await page.evaluate("() => document.body?.innerText?.toLowerCase() || ''"))[:2000]
        return any(sig in content for sig in _BLOCK_SIGNATURES)
    except Exception:
        return False


def _notify_google_block(keyword: str, collected_so_far: int) -> None:
    """Envoie une alerte Telegram quand Google bloque le scraper."""
    try:
        from core.telegram_adapter import notify
        msg = (
            f"🚨 *Google ADS bloqué (403)*\n"
            f"Mot-clé en cours : `{keyword}`\n"
            f"Leads déjà collectés : {collected_so_far}\n"
            f"Le pipeline s'est arrêté proprement.\n"
            f"💡 Résoudre le captcha dans Chrome Gemini puis relancer."
        )
        notify(msg)
    except Exception as e:
        logger.warning(f"AdsExtractor: Telegram alert failed — {e}")


# ─── Comportement humain simulé (warmup, délais, souris) ───────────────────

_WARMUP_SITES = [
    "https://www.lemonde.fr",
    "https://www.lefigaro.fr",
    "https://www.20minutes.fr",
    "https://www.bfmtv.com",
]


async def _human_delay(min_ms: int = 800, max_ms: int = 2500):
    """Pause aléatoire comme un temps de réaction humain."""
    await asyncio.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


async def _move_mouse(page):
    """Simule quelques mouvements de souris naturels."""
    try:
        for _ in range(random.randint(2, 4)):
            x = random.randint(200, 1500)
            y = random.randint(100, 700)
            await page.mouse.move(x, y, steps=random.randint(10, 25))
            await _human_delay(100, 400)
    except Exception:
        pass


async def _warmup_page(page):
    """Visite un site neutre avant Google pour créer une session réaliste."""
    try:
        site = random.choice(_WARMUP_SITES)
        await page.goto(site, wait_until="domcontentloaded", timeout=20_000)
        await _human_delay(3000, 6000)
        await page.mouse.wheel(0, random.randint(200, 500))
        await _human_delay(1500, 3000)
        await _move_mouse(page)
    except Exception:
        pass


async def _extract_from_google(
    page, browser, keyword: str, country: str, max_per_kw: int,
    pages_per_kw: int = _MAX_PAGES_SAFETY,
    log_callback: Optional[callable] = None
) -> tuple:
    """
    Parcourt toutes les pages Google jusqu'à épuisement des annonces.
    Retourne (domains, page, was_blocked) :
      was_blocked=True  → captcha/erreur réseau (à signaler à l'appelant)
      was_blocked=False → pages scannées normalement, même si 0 annonces
    """
    params   = COUNTRY_PARAMS.get(country, COUNTRY_PARAMS["fr"])
    
    search_query = keyword

    base_url = f"https://www.{params['domain']}/search?q={search_query}&gl={params['gl']}&hl={params['hl']}&num=20"

    domains     = []
    seen        = set()
    max_pages   = min(pages_per_kw, _MAX_PAGES_SAFETY)
    was_blocked = False

    # JS : détecte si Google a encore des résultats organiques sur la page
    # Signal fiable pour "vraie dernière page" — indépendant de la présence d'annonces
    _JS_HAS_ORGANIC = """
        () => {
            // Résultats organiques présents : div#search avec au moins un lien h3
            const search = document.querySelector('#search');
            if (!search) return false;
            return search.querySelectorAll('h3').length > 0;
        }
    """

    for page_idx in range(max_pages):
        if _is_stop_requested():
            if log_callback: log_callback(f"Arrêt demandé pendant l'extraction de '{keyword}'", "warning")
            logger.info("AdsExtractor: arrêt d'urgence pendant la pagination.")
            break

        if len(domains) >= max_per_kw:
            break

        start = page_idx * 10
        url   = base_url if page_idx == 0 else f"{base_url}&start={start}"

        try:
            from core.browser import wait_for_captcha_clear
            await wait_for_captcha_clear()

            # Navigation vers Google
            await _move_mouse(page)
            await _human_delay(500, 1500)
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            # Attendre le chargement des annonces JS asynchrones
            await _human_delay(2000, 4500)
            await _move_mouse(page)

            # ── Détection 403 / blocage Google ────────────────────────────────
            if await _is_google_blocked(page):
                msg = f"Google 403 (bloqué) détecté pour '{keyword}' p{page_idx+1}"
                logger.error(msg)
                if log_callback: log_callback(msg, "error")
                _notify_google_block(keyword, len(domains))
                _request_stop()
                was_blocked = True
                break

            # Scroll progressif non déterministe — déclenche le lazy-load des #bottomads
            # Google utilise IntersectionObserver : pas de pattern prévisible
            scroll_steps = random.randint(3, 6)
            for _step in range(scroll_steps):
                ratio = (_step + 1) / scroll_steps + random.uniform(-0.08, 0.08)
                ratio = max(0.1, min(1.0, ratio))
                await page.evaluate(f"() => window.scrollTo(0, document.body.scrollHeight * {ratio})")
                await page.wait_for_timeout(random.randint(600, 1800))
            # Remonter en haut occasionnellement (pas toujours)
            if random.random() < 0.6:
                _scroll_back = random.randint(0, 200)
                await page.evaluate(f"() => window.scrollTo(0, {_scroll_back})")
                await page.wait_for_timeout(random.randint(500, 1200))
        except Exception as e:
            logger.warning(f"Google '{keyword}' p{page_idx+1} navigation échouée: {e}")
            try:
                await page.evaluate("() => window.stop()")
                await asyncio.sleep(0.5)
            except Exception:
                pass
            # Navigation totalement morte : rouvrir un onglet, fermer l'ancien
            old_page = page
            try:
                page = await old_page.context.new_page()
                await patch_page(page)
                logger.info(f"Google '{keyword}' p{page_idx+1} — nouvel onglet ouvert (même profil)")
            except Exception as reopen_err:
                logger.error(f"Google '{keyword}' — impossible de rouvrir un onglet : {reopen_err}")
            finally:
                try:
                    await old_page.close()
                except Exception:
                    pass
            was_blocked = True
            break

        content_len = await page.evaluate("() => document.body.innerHTML.length")
        is_captcha  = await page.evaluate(_JS_IS_CAPTCHA)

        if is_captcha or content_len < 20000:
            was_blocked = True
            page = await _handle_captcha_page(page, label=f"Google Ads — {keyword}")
            try:
                await page.goto(url, wait_until="commit", timeout=30_000)
                await page.wait_for_timeout(2000)
                if await page.evaluate(_JS_IS_CAPTCHA):
                    break
                was_blocked = False
            except Exception:
                break

        # ── Vérifier si Google a encore des résultats organiques ──────────────
        # C'est le seul signal fiable de "vraie dernière page".
        # L'absence d'annonces sur une page ne signifie PAS qu'il n'y en aura plus.
        has_organic = await page.evaluate(_JS_HAS_ORGANIC)
        if not has_organic and page_idx > 0:
            msg = f"'{keyword}' p{page_idx+1} — fin des résultats Google"
            if log_callback: log_callback(msg, "info")
            logger.info(msg)
            break

        raw_urls: List[str] = await page.evaluate(_JS_EXTRACT_ADS) or []
        found_this_page = 0
        for href in raw_urls:
            domain = _clean_url(href)
            if domain and domain not in seen:
                seen.add(domain)
                domains.append(domain)
                found_this_page += 1

        msg = f"'{keyword}' p{page_idx+1} -> {found_this_page} annonceurs (total {len(domains)})"
        if log_callback: log_callback(msg, "info")
        logger.info(msg)

        if found_this_page == 0:
            logger.info(f"Google '{keyword}' — fin des résultats (aucun nouveau lead)")
            break

        if page_idx < max_pages - 1:
            await asyncio.sleep(random.uniform(2.0, 5.0))

    return domains[:max_per_kw], page, was_blocked


async def _extract_from_bing(page, keyword: str, country: str, max_per_kw: int) -> List[str]:
    """Extraction de secours depuis Bing (structure plus stable)."""
    lang = "fr" if country in ("fr", "be", "ch", "lu") else "en"
    
    country_names = {"fr": "France", "ch": "Suisse", "be": "Belgique", "lu": "Luxembourg"}
    c_name = country_names.get(country.lower(), "")
    if c_name and c_name.lower() not in keyword.lower():
        search_query = f"{keyword} {c_name}"
    else:
        search_query = keyword
        
    url = f"https://www.bing.com/search?q={search_query}&mkt={lang}-{country.upper()}&count=10"

    try:
        from scraper.sniper.pipeline import is_stop_requested
        if is_stop_requested():
            return []
            
        await page.goto(url, wait_until="domcontentloaded", timeout=25_000)
        await page.wait_for_timeout(2000)
    except Exception as e:
        logger.warning(f"Bing navigation échouée pour '{keyword}': {e}")
        return []

    raw_links: List[str] = await page.evaluate("""
        () => {
            const results = [];
            document.querySelectorAll('.b_ad a[href], li.b_ad a[href]').forEach(a => {
                if (a.href && !a.href.includes('bing.com') && !a.href.startsWith('#'))
                    results.push(a.href);
            });
            return [...new Set(results)];
        }
    """) or []

    domains = []
    seen = set()
    for href in raw_links:
        domain = _clean_url(href)
        if domain and domain not in seen:
            seen.add(domain)
            domains.append(domain)
            if len(domains) >= max_per_kw:
                break

    logger.info(f"Bing '{keyword}' -> {len(domains)} domaines annonceurs")
    return domains


# ─── Connexion CDP (déléguée à core/browser) ─────────────────────────────────

import sys as _sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in _sys.path:
    _sys.path.insert(0, ROOT)


async def _get_cdp_browser():
    """Retourne le browser CDP connecté au Chrome Gemini."""
    try:
        from core.browser import get_async_browser
        return await get_async_browser()
    except Exception as e:
        logger.error(f"Chrome Gemini non disponible : {e}")
        return None


async def extract_ads_async(
    keywords: List[str],
    country: str = "fr",
    max_per_kw: int = 9999,
    pages_per_kw: int = _MAX_PAGES_SAFETY,
    use_bing_fallback: bool = True,
    on_lead_callback: Optional[callable] = None,
    log_callback: Optional[callable] = None,
) -> List[Dict]:
    """
    Extrait TOUS les annonceurs disponibles pour chaque mot-clé.
    Utilise la connexion CDP vers Chrome Gemini — **profil persistant** (Profile 1).
    Chaque mot-clé reçoit un **nouvel onglet** dans le même contexte utilisateur,
    afin que Google reconnaisse le même navigateur / mêmes cookies.

    Returns:
        [{"domaine": str, "mot_cle": str, "pays": str}, ...]
    """
    results: List[Dict] = []
    all_seen_domains: set = set()

    # Tuer les anciennes instances Chrome pour éviter l'accumulation de processus
    try:
        from core.browser import close_async_browsers
        await close_async_browsers()
    except Exception:
        pass
    try:
        from core.open_chrome import kill_chrome
        kill_chrome()
    except Exception as e:
        logger.warning(f"[ads_extractor] Échec kill_chrome: {e}")

    browser = await _get_cdp_browser()
    if browser is None:
        return []

    # Nettoyer les cookies Google pour éviter le shadow-ban
    try:
        if browser.contexts:
            ctx = browser.contexts[0]
            await ctx.clear_cookies()
            logger.info("[ads_extractor] Cookies Profile 1 vidés — session Google réinitialisée")
    except Exception as e:
        logger.warning(f"[ads_extractor] Échec nettoyage cookies: {e}")

    # Vérifier que le contexte est bien vivant, sinon redémarrer Chrome
    try:
        if not browser.contexts:
            logger.warning("[ads_extractor] Contexte CDP vide après nettoyage — redémarrage Chrome")
            from core.browser import get_async_browser
            browser = await get_async_browser(force_restart=True)
    except Exception as e:
        logger.error(f"[ads_extractor] Contexte CDP mort: {e}")
        from core.browser import get_async_browser
        browser = await get_async_browser(force_restart=True)

    try:
        for kw in keywords:
            if _is_stop_requested():
                if log_callback: log_callback("Arrêt détecté (changement de mot-clé)", "warning")
                logger.info("AdsExtractor: arrêt d'urgence détecté entre deux mots-clés.")
                break

            # Nouvel onglet dans le profil par défaut (Profile 1) — mêmes cookies, historique, session
            # Utilise browser.contexts[0] = contexte du profil, PAS incognito
            ctx = browser.contexts[0] if browser.contexts else None
            if ctx is None:
                logger.warning("[ads_extractor] Contexte CDP vide, attente 2s...")
                await asyncio.sleep(2)
                ctx = browser.contexts[0] if browser.contexts else None
            if ctx is None:
                logger.error("[ads_extractor] Aucun contexte CDP disponible — extraction impossible")
                continue
            page = await ctx.new_page()
            await patch_page(page)

            try:
                if log_callback: log_callback(f"Extraction : {kw}...", "info")

                domains, page, was_blocked = await asyncio.wait_for(
                    _extract_from_google(page, browser, kw, country, max_per_kw, pages_per_kw, log_callback=log_callback),
                    timeout=_KEYWORD_TIMEOUT
                )

                if not domains:
                    if was_blocked:
                        if use_bing_fallback:
                            logger.info(f"Google bloqué pour '{kw}' — tentative Bing")
                            domains = await asyncio.wait_for(
                                _extract_from_bing(page, kw, country, max_per_kw),
                                timeout=_KEYWORD_TIMEOUT
                            )
                        else:
                            logger.info(f"Google bloqué pour '{kw}' — keyword ignoré")
                    else:
                        logger.info(f"Aucune annonce Google pour '{kw}' — Bing ignoré")

                for domain in domains:
                    if domain not in all_seen_domains:
                        all_seen_domains.add(domain)
                        lead_obj = {
                            "domaine":  domain,
                            "mot_cle":  kw,
                            "pays":     country,
                        }
                        results.append(lead_obj)
                        if on_lead_callback:
                            try:
                                on_lead_callback(lead_obj)
                            except Exception:
                                pass

            except Exception as e:
                logger.error(f"Erreur extraction pour '{kw}': {e}")
            finally:
                # Fermer l'onglet pour éviter l'accumulation
                try:
                    _p = page
                except UnboundLocalError:
                    _p = None
                if _p is not None:
                    try:
                        await _p.close()
                    except Exception:
                        pass

    finally:
        # Fermer la connexion CDP pour éviter l'accumulation de connexions
        # Chrome (Profile 1) continue de tourner — les cookies/sessions sont préservées
        # La prochaine extraction rouvrira une connexion fraîche via get_async_browser()
        try:
            from core.browser import close_async_browsers
            await close_async_browsers()
        except Exception:
            pass

    logger.info(f"Total annonceurs extraits : {len(results)}")
    return results


def extract_ads(
    keywords: List[str],
    country: str = "fr",
    max_per_kw: int = 9999,
    pages_per_kw: int = _MAX_PAGES_SAFETY,
    use_bing_fallback: bool = True,
    on_lead_callback: Optional[callable] = None,
    log_callback: Optional[callable] = None,
) -> List[Dict]:
    """Wrapper synchrone pour extract_ads_async."""
    return asyncio.run(
        extract_ads_async(keywords, country, max_per_kw, pages_per_kw, use_bing_fallback, on_lead_callback, log_callback)
    )
