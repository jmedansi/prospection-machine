# -*- coding: utf-8 -*-
"""
Module scraper/email_finder.py
Recherche robuste d'emails sur le site web du prospect.
CHAINAGE DE METHODES PAR PRIORITE:
1. Multi-pages site web (contact, mentions-legales, etc.)
2. Patterns emails cachés (anti-spam)
3. Hunter.io API (si clé disponible)
4. SMTP guess (validation domaine MX)
5. Recherche basique homepage (fallback)
"""

import re
import os
import requests
try:
    import dns.resolver
    _DNS_AVAILABLE = True
except ImportError:
    _DNS_AVAILABLE = False
import socket
from urllib.parse import urljoin, urlparse
from time import time, sleep
from concurrent.futures import ThreadPoolExecutor, as_completed

# email-scraper : gère atob(), entités HTML, mailto: en un seul appel
try:
    from email_scraper import scrape_emails as _lib_scrape_emails
    _EMAIL_SCRAPER_LIB = True
except ImportError:
    _EMAIL_SCRAPER_LIB = False

# Patchright (Playwright anti-détection) pour les sites JS et cookie-wall
try:
    from patchright.sync_api import sync_playwright as _sync_playwright
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    try:
        from playwright.sync_api import sync_playwright as _sync_playwright
        _PLAYWRIGHT_AVAILABLE = True
    except ImportError:
        _PLAYWRIGHT_AVAILABLE = False

# ===========================================================
# CONSTANTES
# ===========================================================

TIMEOUT_GLOBAL = 45
TIMEOUT_PAGE = 10
TIMEOUT_SMTP = 8

PAGES_TO_SCRAPE = [
    # Contact — variantes FR
    "/contact", "/contact/", "/contact.html", "/contact.php",
    "/nous-contacter", "/nous-contacter/", "/nous-contacter.html",
    "/contactez-nous", "/contactez-nous/", "/contactez_nous",
    "/joindre-nous", "/joindre", "/joindre/",
    "/coordonnees", "/coordonnees/", "/coordonnees.html",
    "/infos-pratiques", "/infos", "/infos/",
    # Contact — variantes EN
    "/contact-us", "/contact-us/", "/contact_us",
    "/get-in-touch", "/reach-us", "/reach-out",
    "/contactus", "/contactus.html",
    # À propos — souvent le contact y est
    "/a-propos", "/a-propos/", "/qui-sommes-nous", "/qui-sommes-nous/",
    "/about", "/about/", "/about-us", "/about-us/", "/about_us",
    "/equipe", "/notre-equipe", "/team",
    # Mentions légales — contient souvent un email RGPD
    "/mentions-legales", "/mentions-legales/", "/mentions-legales.html",
    "/mentions_legales", "/mentions_legales/",
    "/legal", "/legal/", "/legales",
    "/politique-de-confidentialite", "/confidentialite",
    "/privacy", "/privacy-policy",
    # Autres
    "/footer", "/plan-du-site", "/sitemap",
    "",  # Home
]

EMAIL_EXCLUDE_PATTERNS = [
    'noreply@', 'no-reply@', 'donotreply@', 'webmaster@', 'abuse@',
    'wordpress@', 'admin@', 'root@', 'postmaster@',
    '@sentry.io', '@googleapis.com', '@google-analytics.com',
    '@facebook.com', '@twitter.com', '@instagram.com', '@linkedin.com',
    '@wix.com', '@squarespace.com', '@wixsite.com', '@weebly.com', '@shopify.com',
    '@mysite.com', '@votresite.com', '@monsite.com', '@yoursite.com',
    '@example.com', '@domain.com', '@test.com', '@localhost',
    '@5.1.3', '@4.0', '@1.16.1', '@3.', '@2.', '@1.',
    'bootstrap', 'popper.js', 'jquery', 'fontawesome', 'googleads',
    # Domaines temporaires / jetables
    'yopmail.com', '10minutemail.com', 'temp-mail.org', 'guerrillamail.com',
    'mailinator.com', 'tempmail.com', 'fakeinbox.com', 'throwaway.email',
    'dispostable.com', 'sharklasers.com', 'spam4.me', 'grr.la',
]


EMAIL_PRIORITY = {
    'contact@': 1,
    'info@': 2,
    'bonjour@': 3,
    'hello@': 4,
    'accueil@': 5,
    'direction@': 6,
    'secretariat@': 7,
    'commercial@': 8,
    'vente@': 9,
}

SMTP_VARIANTS = [
    'contact@{domain}',
    'info@{domain}',
    'bonjour@{domain}',
    'hello@{domain}',
    'accueil@{domain}',
    'direction@{domain}',
]

MASKED_EMAIL_PATTERNS = [
    r'([a-zA-Z0-9._%+-]+)\s*\[at\]\s*([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
    r'([a-zA-Z0-9._%+-]+)\s*\(at\)\s*([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
    r'([a-zA-Z0-9._%+-]+)\s*@\s*([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\s*\(pas\s+de\s+spam\)',
    r'([a-zA-Z0-9._%+-]+)\s*@\s*([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\s*\[pas\s+de\s+spam\]',
    r'([a-zA-Z0-9._%+-]+)\s* arobase \s*([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
    r'([a-zA-Z0-9._%+-]+)\s*\被告\s*([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
    r'([a-zA-Z0-9._%+-]+)\s* CHEZ \s*([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
    r'([a-zA-Z0-9._%+-]+)\s* at \s*([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
    r'([a-zA-Z0-9._%+-]+)\s*\uff40\s*([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
    # Accept-Encoding volontairement absent : si on envoie "br" (brotli), certains serveurs
    # répondent en brotli que requests ne sait pas décompresser sans lib optionnelle.
    # requests gère gzip/deflate seul par défaut — suffisant.
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}

# ===========================================================
# FONCTION PRINCIPALE UNIFIEE
# ===========================================================

def find_email_all_methods(url: str, verbose: bool = False) -> dict:
    """
    Trouve un email en essayant TOUTES les méthodes disponibles.
    S'arrête dès qu'un email est trouvé.

    ORDRE DE PRIORITE:
    1. Scraping multi-pages du site web
    2. Patterns emails masqués (anti-spam)
    3. Hunter.io API
    4. SMTP guess (validation MX)
    5. Scraping homepage simple (fallback)

    Args:
        url: URL du site web
        verbose: Si True, affiche les tentatives

    Returns:
        dict: {email, source, priority, methods_tried}
    """
    global _global_start
    _global_start = time()
    start_time = _global_start
    
    if not url:
        return _empty_result()
    
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    domain = urlparse(url).netloc.replace('www.', '')
    if not domain:
        return _empty_result()
    
    methods_tried = []
    
    if verbose:
        print(f"[EMAIL FINDER] Début recherche pour {domain}")
    
    # ============================================
    # METHODE 1: Scraping multi-pages du site
    # ============================================
    if _time_left(start_time, 25):
        methods_tried.append('multi_pages')
        if verbose:
            print(f"[EMAIL FINDER] Méthode 1: Scraping multi-pages...")
        
        result = _scrape_all_pages(url, domain)
        if result['email']:
            result['methods_tried'] = methods_tried
            if verbose:
                print(f"[EMAIL FINDER] ✓ Trouvé via {result['source']}")
            return result
    
    # ============================================
    # METHODE 1b: Suivi des liens "contact" internes
    # ============================================
    if _time_left(start_time, 22):
        methods_tried.append('link_follow')
        result = _follow_contact_links(url, domain)
        if result['email']:
            result['methods_tried'] = methods_tried
            if verbose:
                print(f"[EMAIL FINDER] ✓ Trouvé via lien contact interne: {result['source']}")
            return result

    # ============================================
    # METHODE 1c: Playwright browser fallback (JS / cookie-wall)
    # ============================================
    if _PLAYWRIGHT_AVAILABLE and _time_left(start_time, 18):
        methods_tried.append('browser_fallback')
        if verbose:
            print(f"[EMAIL FINDER] Méthode 1c: Browser Playwright (parallèle)...")
        emails = _scrape_page_with_browser(url, domain)
        if emails:
            result = {
                'email': emails[0],
                'source': 'browser',
                'priority': _get_priority(emails[0]),
                'methods_tried': methods_tried
            }
            if verbose:
                print(f"[EMAIL FINDER] ✓ Trouvé via browser: {result['email']}")
            return result

    # ============================================
    # METHODE 2: Patterns masqués anti-spam
    # ============================================
    if _time_left(start_time, 20):
        methods_tried.append('masked_patterns')
        if verbose:
            print(f"[EMAIL FINDER] Méthode 2: Patterns masqués...")
        
        result = _find_masked_emails(url, domain)
        if result['email']:
            result['methods_tried'] = methods_tried
            if verbose:
                print(f"[EMAIL FINDER] ✓ Trouvé via {result['source']}")
            return result
    
    # ============================================
    # METHODE 3: Hunter.io API
    # ============================================
    if _time_left(start_time, 15):
        methods_tried.append('hunter')
        if verbose:
            print(f"[EMAIL FINDER] Méthode 3: Hunter.io...")
        
        result = _try_hunter(domain)
        if result['email']:
            result['methods_tried'] = methods_tried
            if verbose:
                print(f"[EMAIL FINDER] ✓ Trouvé via Hunter.io")
            return result
    
    # ============================================
    # METHODE 4: SMTP guess via MX
    # ============================================
    if _time_left(start_time, 8):
        methods_tried.append('smtp_guess')
        if verbose:
            print(f"[EMAIL FINDER] Méthode 4: SMTP guess...")
        
        result = _try_smtp_guess(domain)
        if result['email']:
            result['methods_tried'] = methods_tried
            if verbose:
                print(f"[EMAIL FINDER] ✓ Trouvé via SMTP: {result['email']}")
            return result
    
    # ============================================
    # METHODE 5: Scraping homepage simple
    # ============================================
    if _time_left(start_time, 5):
        methods_tried.append('homepage_basic')
        if verbose:
            print(f"[EMAIL FINDER] Méthode 5: Homepage basique...")
        
        result = _scrape_homepage_basic(url, domain)
        if result['email']:
            result['methods_tried'] = methods_tried
            if verbose:
                print(f"[EMAIL FINDER] ✓ Trouvé via homepage")
            return result
    
    if verbose:
        print(f"[EMAIL FINDER] ✗ Aucun email trouvé après {len(methods_tried)} méthodes")
    
    return _empty_result(methods_tried)


def find_email_on_website(url: str) -> dict:
    """Alias pour compatibilité - utilise find_email_all_methods."""
    return find_email_all_methods(url, verbose=False)


def search_email_on_website(url: str) -> str:
    """Alias pour compatibilité - retourne juste l'email ou None."""
    result = find_email_all_methods(url)
    return result['email']

# ===========================================================
# METHODES INDIVIDUELLES
# ===========================================================

def _scrape_all_pages(url: str, domain: str) -> dict:
    """Scrape toutes les pages critiques du site en parallèle."""
    results = []  # list of (priority, email, source)

    def _fetch(page_path):
        page_url = urljoin(url, page_path)
        found = _scrape_single_page(page_url, domain)
        return [(e, page_path) for e in found]

    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(_fetch, p): p for p in PAGES_TO_SCRAPE}
        for f in as_completed(futures):
            try:
                for email, page_path in f.result():
                    results.append((email, page_path))
            except Exception:
                pass

    if results:
        results.sort(key=lambda x: _get_priority(x[0]))
        best_email, best_page = results[0]
        return {
            'email': best_email,
            'source': f'site:{best_page or "home"}',
            'priority': _get_priority(best_email),
            'methods_tried': []
        }
    return _empty_result()


def _scrape_single_page(page_url: str, domain: str) -> list:
    """Scrape une page et retourne les emails trouvés."""
    emails = []
    try:
        response = requests.get(page_url, headers=HEADERS, timeout=TIMEOUT_PAGE, allow_redirects=True)
        # Accepter 200 et les redirections résolues; ignorer vraies erreurs serveur (5xx)
        if response.status_code >= 500:
            return []
        if response.status_code == 404:
            return []

        text = response.text

        # Suivi des meta-refresh (courant sur les vieux sites artisans FR)
        meta_refresh = re.search(
            r'<meta[^>]+http-equiv=["\']refresh["\'][^>]+content=["\'][^;]*;\s*url=([^"\'>\s]+)',
            text, re.IGNORECASE
        )
        if meta_refresh and len(text) < 5000:  # page de redirection pure
            from urllib.parse import urljoin as _urljoin
            redirect_url = _urljoin(page_url, meta_refresh.group(1).strip())
            try:
                response2 = requests.get(redirect_url, headers=HEADERS, timeout=TIMEOUT_PAGE, allow_redirects=True)
                if response2.status_code == 200:
                    text = response2.text
            except Exception:
                pass

        # 1. Liens mailto:
        emails.extend(re.findall(
            r'href=["\']?mailto:([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})["\']?',
            text, re.IGNORECASE
        ))

        # 2. Attributs data-email / data-mail (obfuscation courante)
        emails.extend(re.findall(
            r'data-(?:email|mail|e-mail)=["\']([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})["\']',
            text, re.IGNORECASE
        ))

        # 3. JSON-LD / Schema.org ContactPoint
        import json as _json
        for ld_block in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', text, re.DOTALL | re.IGNORECASE):
            try:
                data = _json.loads(ld_block)
                if isinstance(data, dict):
                    data = [data]
                if isinstance(data, list):
                    for item in data:
                        for key in ('email', 'contactPoint'):
                            val = item.get(key)
                            if isinstance(val, str) and '@' in val:
                                emails.append(val)
                            elif isinstance(val, dict):
                                e = val.get('email')
                                if e and '@' in e:
                                    emails.append(e)
                            elif isinstance(val, list):
                                for cp in val:
                                    if isinstance(cp, dict):
                                        e = cp.get('email')
                                        if e and '@' in e:
                                            emails.append(e)
            except Exception:
                pass

        # 4. Emails dans le texte (regex classique)
        emails.extend(re.findall(r'\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b', text))

        # 5. Emails masqués anti-spam
        for pattern in MASKED_EMAIL_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for m in matches:
                emails.append(f"{m[0].strip()}@{m[1].strip()}")

        # 6. email-scraper library (atob(), entités HTML, ROT13, etc.)
        if _EMAIL_SCRAPER_LIB:
            try:
                lib_emails = _lib_scrape_emails(text)
                emails.extend(lib_emails)
            except Exception:
                pass

        emails = _filter_emails(emails, domain)

    except Exception:
        pass

    return emails


def _follow_contact_links(url: str, domain: str) -> dict:
    """Cherche des liens internes contenant 'contact' ou 'coordonnees' sur la homepage et les suit."""
    CONTACT_KEYWORDS = ('contact', 'coordonnees', 'joindre', 'nous-contacter', 'mentions', 'about', 'a-propos')
    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT_PAGE, allow_redirects=True)
        if response.status_code != 200:
            return _empty_result()
        text = response.text
        # Extraire tous les href internes
        hrefs = re.findall(r'href=["\']([^"\'#?]+)["\']', text, re.IGNORECASE)
        candidate_urls = []
        base = urlparse(url).scheme + '://' + urlparse(url).netloc
        for href in hrefs:
            href_lower = href.lower()
            if any(kw in href_lower for kw in CONTACT_KEYWORDS):
                full_url = href if href.startswith('http') else urljoin(base + '/', href.lstrip('/'))
                if urlparse(full_url).netloc.replace('www.', '') == domain:
                    candidate_urls.append(full_url)
        # Dédupliquer et limiter
        seen = set()
        for candidate in candidate_urls[:6]:
            if candidate in seen:
                continue
            seen.add(candidate)
            if time() - _global_start >= TIMEOUT_GLOBAL:
                break
            emails = _scrape_single_page(candidate, domain)
            if emails:
                emails.sort(key=lambda e: _get_priority(e))
                path = urlparse(candidate).path or '/'
                return {
                    'email': emails[0],
                    'source': f'link:{path}',
                    'priority': _get_priority(emails[0]),
                    'methods_tried': []
                }
    except Exception:
        pass
    return _empty_result()


def _find_masked_emails(url: str, domain: str) -> dict:
    """Cherche les emails masqués anti-spam sur toutes les pages."""
    for page in PAGES_TO_SCRAPE:
        if time() - _global_start < TIMEOUT_GLOBAL:
            page_url = urljoin(url, page)
            emails = _find_masked_on_page(page_url, domain)
            if emails:
                emails.sort(key=lambda e: _get_priority(e))
                return {
                    'email': emails[0],
                    'source': f'masked:{page or "home"}',
                    'priority': _get_priority(emails[0]),
                    'methods_tried': []
                }
    return _empty_result()


def _find_masked_on_page(page_url: str, domain: str) -> list:
    """Cherche les patterns d'emails masqués sur une page."""
    emails = []
    try:
        response = requests.get(page_url, headers=HEADERS, timeout=TIMEOUT_PAGE, allow_redirects=True)
        if response.status_code != 200:
            return []
        
        text = response.text
        
        for pattern in MASKED_EMAIL_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for m in matches:
                email = f"{m[0].strip()}@{m[1].strip()}"
                emails.append(email)
        
        emails = _filter_emails(emails, domain)
        
    except Exception:
        pass
    
    return emails


def _try_hunter(domain: str) -> dict:
    """Cherche via Hunter.io API."""
    api_key = os.getenv('HUNTER_API_KEY')
    if not api_key:
        return _empty_result()
    
    try:
        response = requests.get(
            'https://api.hunter.io/v2/domain-search',
            params={'domain': domain, 'api_key': api_key},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            emails = data.get('data', {}).get('emails', [])
            if emails:
                email_data = emails[0]
                return {
                    'email': email_data.get('value'),
                    'source': 'hunter_api',
                    'priority': _get_priority(email_data.get('value', '')),
                    'methods_tried': []
                }
    except Exception:
        pass
    
    return _empty_result()


def _try_smtp_guess(domain: str) -> dict:
    """Tente de deviner un email via SMTP."""
    if not _DNS_AVAILABLE:
        return _empty_result()
    
    clean_domain = domain.replace('www.', '')
    
    try:
        mx_records = dns.resolver.resolve(clean_domain, 'MX')
        mx_host = str(mx_records[0].exchange).rstrip('.')
    except Exception:
        return _empty_result()
    
    for variant in SMTP_VARIANTS:
        if time() - _global_start > TIMEOUT_GLOBAL:
            break
        email = variant.replace('{domain}', clean_domain)
        if _verify_smtp(mx_host, email):
            return {
                'email': email,
                'source': 'smtp_guess',
                'priority': 15,
                'methods_tried': []
            }
    
    return _empty_result()


def _scrape_homepage_basic(url: str, domain: str) -> dict:
    """Fallback: scraping simple de la homepage."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT_PAGE, allow_redirects=True)
        if response.status_code != 200:
            return _empty_result()
        
        emails_trouves = re.findall(
            r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b',
            response.text
        )
        
        faux_positifs = ['noreply', 'no-reply', 'donotreply', 'admin', 'webmaster', 
                        'sentry', 'wix', 'example', 'domain.com', 'googleads']
        
        for email in emails_trouves:
            email_lower = email.lower()
            if not any(fp in email_lower for fp in faux_positifs):
                return {
                    'email': email,
                    'source': 'homepage_basic',
                    'priority': _get_priority(email),
                    'methods_tried': []
                }
    except Exception:
        pass
    
    return _empty_result()


_COOKIE_SELECTORS_SYNC = [
    'button[aria-label*="Tout accepter"]',
    'button[aria-label*="Accept all"]',
    '#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll',
    '#onetrust-accept-btn-handler',
    'button.onetrust-close-btn-handler',
    '.axeptio_btn_acceptAll',
    '#didomi-notice-agree-button',
    '.tarteaucitronAllow',
    'button:text("Tout accepter")', 'button:text("Accepter tout")',
    'button:text("Accepter")', "button:text(\"J'accepte\")",
    'button:text("Accept all")', 'button:text("Accept")',
    'button:text("I agree")', 'button:text("Got it")',
    'button[id*="accept-all"]', 'button[id*="acceptAll"]',
    'button[class*="accept-all"]', 'button[class*="acceptAll"]',
    'button[data-testid*="accept"]',
]


def _dismiss_cookies_sync(page):
    """Ferme les bandeaux cookie sur la page synchrone."""
    try:
        page.wait_for_timeout(800)
        for sel in _COOKIE_SELECTORS_SYNC:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    page.wait_for_timeout(500)
                    return
            except Exception:
                continue
    except Exception:
        pass


_BROWSER_PAGES = [
    '/contact', '/contact/', '/nous-contacter', '/contactez-nous',
    '/contact-us', '/mentions-legales', '/about', '/a-propos', '',
]


def _extract_emails_from_html(html: str, domain: str) -> list:
    """Extrait et filtre les emails depuis du HTML brut."""
    emails = []
    emails.extend(re.findall(
        r'href=["\']?mailto:([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})["\']?',
        html, re.IGNORECASE
    ))
    emails.extend(re.findall(r'\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b', html))
    if _EMAIL_SCRAPER_LIB:
        try:
            emails.extend(_lib_scrape_emails(html))
        except Exception:
            pass
    return _filter_emails(emails, domain)


def _scrape_page_with_browser(base_url: str, domain: str) -> list:
    """
    Fallback Playwright pour les sites JS-rendus ou bloqués par cookie-wall.
    Lance un seul navigateur avec N onglets en parallèle (threads).
    """
    if not _PLAYWRIGHT_AVAILABLE:
        return []

    all_emails = []

    try:
        with _sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)

            def scrape_tab(path):
                try:
                    ctx = browser.new_context(
                        user_agent=HEADERS['User-Agent'],
                        locale='fr-FR',
                        viewport={'width': 1280, 'height': 800},
                    )
                    tab = ctx.new_page()
                    tab.goto(urljoin(base_url, path), wait_until='domcontentloaded', timeout=15000)
                    _dismiss_cookies_sync(tab)
                    tab.wait_for_timeout(1000)
                    # Hover sur icônes mail pour déclencher tooltip/affichage JS
                    for sel in ['[class*="mail"]', '[class*="email"]', 'a[href^="mailto:"]']:
                        try:
                            for el in tab.query_selector_all(sel)[:3]:
                                try:
                                    el.hover()
                                    tab.wait_for_timeout(200)
                                except Exception:
                                    pass
                        except Exception:
                            pass
                    html = tab.content()
                    ctx.close()
                    return _extract_emails_from_html(html, domain)
                except Exception:
                    return []

            with ThreadPoolExecutor(max_workers=4) as ex:
                futures = [ex.submit(scrape_tab, p) for p in _BROWSER_PAGES]
                for f in as_completed(futures):
                    try:
                        all_emails.extend(f.result())
                    except Exception:
                        pass

            browser.close()

    except Exception:
        pass

    # Dédupliquer et trier
    seen = set()
    deduped = []
    for e in all_emails:
        if e not in seen:
            seen.add(e)
            deduped.append(e)
    deduped.sort(key=lambda e: _get_priority(e))
    return deduped


def _verify_smtp(mx_host: str, email: str) -> bool:
    """Vérifie si un email est valide via connexion SMTP simple."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT_SMTP)
        sock.connect((mx_host, 25))
        
        resp = sock.recv(1024).decode('utf-8', errors='ignore')
        if not resp.startswith('220'):
            sock.close()
            return False
        
        sock.send(b'HELO test\r\n')
        resp = sock.recv(1024).decode('utf-8', errors='ignore')
        if not resp.startswith('250'):
            sock.close()
            return False
        
        sock.send(b'MAIL FROM:<test@test.com>\r\n')
        resp = sock.recv(1024).decode('utf-8', errors='ignore')
        if not resp.startswith('250'):
            sock.close()
            return False
        
        sock.send(f'RCPT TO:<{email}>\r\n'.encode())
        resp = sock.recv(1024).decode('utf-8', errors='ignore')
        
        sock.send(b'QUIT\r\n')
        sock.close()
        
        return resp.startswith('250')
        
    except Exception:
        return False


# ===========================================================
# UTILITAIRES
# ===========================================================

_global_start = time()

def _time_left(start_time: float, min_needed: float) -> bool:
    """Vérifie s'il reste assez de temps."""
    return (time() - start_time) < (TIMEOUT_GLOBAL - min_needed)


def _filter_emails(emails: list, domain: str) -> list:
    """
    Garde tout email valide trouvé sur la page, sauf les emails système évidents.

    Règle : un professionnel qui cherche des clients ne met jamais un faux email
    sur son site. Si c'est sur la page, c'est son email.

    Seuls les patterns EMAIL_EXCLUDE_PATTERNS sont rejetés (noreply, wix, sentry…).
    Aucun filtrage par domaine — un artisan peut avoir son site sur .fr et son
    email sur gmail, wanadoo, ou un domaine complètement différent.
    """
    seen = set()
    result = []

    for email in emails:
        email = email.lower().strip()

        if email in seen:
            continue
        seen.add(email)

        if '@' not in email or '.' not in email.split('@')[1]:
            continue

        # Rejeter les faux positifs évidents (chemins d'image, fragments HTML, etc.)
        local, domain_part = email.split('@', 1)
        # Extensions de fichiers qui ne sont pas des TLDs valides
        _FILE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'ico', 'bmp',
                             'pdf', 'zip', 'js', 'css', 'php', 'html', 'htm', 'xml',
                             'mp4', 'mp3', 'mov', 'avi', 'woff', 'ttf', 'eot'}
        tld = domain_part.rsplit('.', 1)[-1].lower()
        if not tld.isalpha() or len(tld) < 2 or len(tld) > 6:
            continue
        if tld in _FILE_EXTENSIONS:
            continue
        # Local part ne doit pas contenir de slash ou backslash
        if '/' in local or '\\' in local:
            continue
        # Longueur minimale réaliste : au moins 2 chars dans local, domaine complet >= 6 chars
        if len(local) < 2 or len(domain_part) < 6:
            continue

        if any(excl in email for excl in EMAIL_EXCLUDE_PATTERNS):
            continue

        result.append(email)

    return result


def _get_priority(email: str) -> int:
    """Retourne la priorité d'un email (1 = meilleur)."""
    email_lower = email.lower()
    for pattern, priority in EMAIL_PRIORITY.items():
        if email_lower.startswith(pattern):
            return priority
    return 10


def _empty_result(methods_tried: list = None) -> dict:
    """Retourne un résultat vide standardisé."""
    return {
        'email': None,
        'source': 'none',
        'priority': 999,
        'methods_tried': methods_tried or []
    }


def verify_email(email: str) -> str:
    """Vérifie si un email est valide (via MX lookup)."""
    if not email or '@' not in email:
        return 'Invalide'

    if not _DNS_AVAILABLE:
        return 'Inconnu'

    try:
        domain = email.split('@')[1].replace('www.', '')
        dns.resolver.resolve(domain, 'MX')
        return 'Valide'
    except Exception:
        return 'Invalide'
