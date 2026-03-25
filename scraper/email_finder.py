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

# ===========================================================
# CONSTANTES
# ===========================================================

TIMEOUT_GLOBAL = 30
TIMEOUT_PAGE = 5
TIMEOUT_SMTP = 8

PAGES_TO_SCRAPE = [
    "/contact",
    "/nous-contacter",
    "/contactez-nous",
    "/contactez_nous",
    "/contact-us",
    "/a-propos",
    "/about",
    "/about-us",
    "/mentions-legales",
    "/mentions_legales",
    "/legal",
    "/footer",
    "",  # Home
]

EMAIL_EXCLUDE_PATTERNS = [
    'noreply@', 'no-reply@', 'donotreply@', 'webmaster@', 'abuse@',
    'wordpress@', 'admin@', 'root@', 'postmaster@',
    '@sentry.io', '@googleapis.com', '@google-analytics.com',
    '@facebook.com', '@twitter.com', '@instagram.com', '@linkedin.com',
    '@wix.com', '@squarespace.com', '@wixsite.com', '@weebly.com', '@shopify.com',
    '@example.com', '@domain.com', '@test.com', '@localhost',
    '@5.1.3', '@4.0', '@1.16.1', '@3.', '@2.', '@1.',
    'bootstrap', 'popper.js', 'jquery', 'fontawesome', 'googleads',
]

EMAIL_INCLUDE_DOMAINS = [
    'gmail.com', 'hotmail.com', 'hotmail.fr', 'outlook.com', 
    'yahoo.com', 'yahoo.fr', 'orange.fr', 'sfr.fr', 'free.fr',
    'laposte.net', 'live.com', 'msn.com',
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
    'contact@{domain}',
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
    'Accept-Encoding': 'gzip, deflate, br',
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
    start_time = time()
    
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
    """Scrape toutes les pages critiques du site."""
    for page in PAGES_TO_SCRAPE:
        if time() - _global_start < TIMEOUT_GLOBAL:
            page_url = urljoin(url, page)
            emails = _scrape_single_page(page_url, domain)
            if emails:
                emails.sort(key=lambda e: _get_priority(e))
                return {
                    'email': emails[0],
                    'source': f'site:{page or "home"}',
                    'priority': _get_priority(emails[0]),
                    'methods_tried': []
                }
    return _empty_result()


def _scrape_single_page(page_url: str, domain: str) -> list:
    """Scrape une page et retourne les emails trouvés."""
    emails = []
    try:
        response = requests.get(page_url, headers=HEADERS, timeout=TIMEOUT_PAGE, allow_redirects=True)
        if response.status_code != 200:
            return []
        
        text = response.text
        text_lower = text.lower()
        
        # 1. Liens mailto:
        mailto_patterns = re.findall(
            r'href=["\']?mailto:([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})["\']?',
            text, re.IGNORECASE
        )
        emails.extend(mailto_patterns)
        
        # 2. Emails dans le texte (regex classique)
        email_pattern = r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b'
        found = re.findall(email_pattern, text)
        emails.extend(found)
        
        # 3. Emails masqués anti-spam
        for pattern in MASKED_EMAIL_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for m in matches:
                emails.append(f"{m[0].strip()}@{m[1].strip()}")
        
        # Filtrer et nettoyer
        emails = _filter_emails(emails, domain)
        
    except Exception:
        pass
    
    return emails


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
    """Filtre les emails invalides et doublons."""
    seen = set()
    result = []
    external_emails = []
    
    for email in emails:
        email = email.lower().strip()
        
        if email in seen:
            continue
        seen.add(email)
        
        if any(excl in email for excl in EMAIL_EXCLUDE_PATTERNS):
            continue
        
        if '@' not in email or '.' not in email.split('@')[1]:
            continue
        
        try:
            email_domain = email.split('@')[1]
            
            if email_domain == domain or domain.endswith(email_domain):
                result.append(email)
            elif any(inc in email_domain for inc in EMAIL_INCLUDE_DOMAINS):
                external_emails.append(email)
        except:
            continue
    
    if not result and external_emails:
        result = external_emails
    
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
    
    try:
        domain = email.split('@')[1].replace('www.', '')
        mx_records = dns.resolver.resolve(domain, 'MX')
        return 'Valide'
    except:
        return 'Invalide'
