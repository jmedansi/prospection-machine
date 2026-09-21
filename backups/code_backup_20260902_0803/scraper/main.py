# -*- coding: utf-8 -*-
"""
Scraper Google Maps via Playwright headless + stealth.
Extrait les établissements locaux et écrit dans Google Sheets (leads_bruts).
Zéro dépendance Gemini — 100% Python + outils spécialisés.
"""
import sys
import os
import argparse
import random
import time
import re
from datetime import datetime
from urllib.parse import quote

import logging
import requests
import psutil

# Ajout du répertoire parent au sys.path pour importer config_manager
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config_manager import get_config

# Module de recherche email avancée (TOUTES les méthodes)
try:
    from scraper.email_finder import (
        find_email_all_methods,
        find_email_on_website,
        search_email_on_website
    )
    _EMAIL_FINDER_AVAILABLE = True
except ImportError:
    _EMAIL_FINDER_AVAILABLE = False

# --- Persistance SQLite (source de vérité principale) ---
try:
    from database.db_manager import insert_lead as db_insert_lead, get_conn as db_get_conn
    _DB_AVAILABLE = True
except ImportError:
    _DB_AVAILABLE = False
    print("[WARN] database/db_manager.py introuvable — SQLite désactivé")

# Configuration du logging
logging.basicConfig(
    filename='errors.log',
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ===========================================================
# HELPERS — Extraction email
# ===========================================================

def _email_confidence(result: dict) -> int:
    """Retourne un score de confiance 0-100 pour un résultat find_email_all_methods."""
    if not result or not result.get('email'):
        return 0
    source = result.get('source', '')
    priority = result.get('priority', 10)
    # Base selon la source
    if source.startswith('site:'):
        base = 85
    elif source.startswith('link:'):
        base = 80
    elif source.startswith('masked:'):
        base = 75
    elif source == 'smtp_guess':
        base = 60
    elif source == 'homepage_basic':
        base = 50
    else:
        base = 40
    # Bonus selon la priorité de l'alias (contact@ > info@ > …)
    bonus = max(0, 10 - priority)
    return min(100, base + bonus)


# ─── Regex téléphones ────────────────────────────────────────────────
_PHONE_FR = r'(?:(?:\+|00)33[\s.-]{0,3}(?:\(0\)[\s.-]{0,3})?|0)[1-9](?:(?:[\s.-]?\d{2}){4}|\d{2}(?:[\s.-]?\d{3}){2})'
_PHONE_BJ = r'(?:\+229[\s.-]?)?(?:21|22|23|24|25|26|27|28|29|30|31|32|33|34|35|36|37|38|39|40|41|42|43|44|45|46|47|48|49|50|51|52|53|54|55|56|57|58|59|60|61|62|63|64|65|66|67|68|69|70|71|72|73|74|75|76|77|78|79|80|81|82|83|84|85|86|87|88|89|90|91|92|93|94|95|96|97|98|99)\d{4}'


def extract_domain(url):
    """Extrait le domaine d'une URL."""
    if not url:
        return None
    from core.domain import extract_domain as _extract
    return _extract(url)


def search_phone_on_website(url, country='fr'):
    """Cherche un numero de telephone sur une page web s'il est manquant sur Google Maps."""
    if not url:
        return None
    try:
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        pattern = _PHONE_BJ if country == 'bj' else _PHONE_FR
        tels_trouves = re.findall(pattern, response.text)
        if tels_trouves:
            return tels_trouves[0].strip()
        return None
    except Exception as e:
        logger.error(f"Erreur recherche telephone sur {url}: {e}")
        return None


def verify_email_mailcheck(email):
    """Vérifie l'email via Mailcheck.ai — gratuit, sans clé."""
    url = f"https://api.mailcheck.ai/email/{email}"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        if data.get('status') == 200 or data.get('mx'):
            return "Valide"
        return "Inconnu"
    except Exception as e:
        logger.error(f"Erreur Mailcheck.ai pour {email}: {e}")
        return "Erreur"


# ─── Rotation session ─────────────────────────────────────────────────────────
_SESSION_PORT = [9300]
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]


def _next_port():
    _SESSION_PORT[0] += 1
    return _SESSION_PORT[0]


def _random_ua():
    return random.choice(_USER_AGENTS)



# ===========================================================
# GEMINI — Extraction Google Maps
# ===========================================================
async def scrape_google_maps(keyword, city, limit=20, known_names=None, country='fr'):
    """
    Scrape Google Maps via Playwright headless dédié (évite les conflits CDP).
    """
    from urllib.parse import quote
    from core.browser import _JS_IS_CAPTCHA, handle_captcha_async
    from playwright.async_api import async_playwright

    places = []
    seen_names = set(known_names) if known_names else set()

    print(f"\n[Maps] Ouverture de la recherche : {keyword} à {city}")

    port = _next_port()
    ua = _random_ua()
    print(f"   session port={port} ua={ua[:60]}...")

    pw = await async_playwright().__aenter__()
    browser = await pw.chromium.launch(
        headless=True,
        args=[
            '--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu', '--no-zygote',
            f'--remote-debugging-port={port}',
            '--disable-blink-features=AutomationControlled',
        ]
    )
    try:
        locale = "fr-BJ" if country == "bj" else "fr-FR"
        ctx = await browser.new_context(
            locale=locale,
            viewport={"width": 1920, "height": 1080},
            user_agent=ua,
        )
        page = await ctx.new_page()

        search_query = quote(f"{keyword} {city}")
        url = f"https://www.google.com/maps/search/{search_query}"

        await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        await page.wait_for_timeout(3000)

        if await page.evaluate(_JS_IS_CAPTCHA):
            print("   [Maps] Captcha détecté, attente résolution...")
            await handle_captcha_async(page, label="Google Maps")

        try:
            await page.wait_for_selector('div[role="feed"]', timeout=10_000)
            for _ in range(8):
                await page.evaluate("() => { const f = document.querySelector('div[role=\"feed\"]'); if(f) f.scrollBy(0, 3000); }")
                await page.wait_for_timeout(1200)
        except:
            pass

        print("   [Maps] Extraction de la liste des résultats...")
        list_data = await page.evaluate(r'''() => {
            const results = [];
            const items = document.querySelectorAll('div[role="article"]');
            items.forEach((item, index) => {
                const titleEl = item.querySelector('.fontHeadlineSmall');
                const linkEl = item.querySelector('a.hfpxzc');
                if (!titleEl || !linkEl) return;

                let rating = 0, nb_avis = 0;

                // Rating from aria-label (primary method)
                const ratingAria = item.querySelector('[aria-label*="étoiles"], [aria-label*="stars"]');
                if (ratingAria) {
                    const label = ratingAria.getAttribute('aria-label') || '';
                    const starM = label.match(/([\d.,]+)/);
                    if (starM) rating = parseFloat(starM[1].replace(',', '.'));
                }
                
                // Fallback: search for star rating in all aria-labels
                if (!rating) {
                    const allArias = item.querySelectorAll('[aria-label]');
                    for (const el of allArias) {
                        const label = el.getAttribute('aria-label') || '';
                        if (/[\d.,]+\s*(étoile|star)/.test(label)) {
                            const m = label.match(/([\d.,]+)/);
                            if (m) { rating = parseFloat(m[1].replace(',', '.')); break; }
                        }
                    }
                }

                // Review count extraction with improved strategies
                const itemText = item.innerText || '';
                const parentText = item.parentElement ? item.parentElement.innerText : '';
                const fullText = itemText + ' ' + parentText;

                // Strategy 1: "• X avis" pattern (current Google Maps France format)
                let bulletMatch = fullText.match(/[\u00b7\u2022]\s*(\d+)\s*avis/i);
                if (bulletMatch) {
                    nb_avis = parseInt(bulletMatch[1]);
                } else {
                    // Strategy 2: just "• X" (generic bullet, only numbers)
                    bulletMatch = fullText.match(/[\u00b7\u2022]\s*(\d+)(?!\s*\w)/);
                    if (bulletMatch) {
                        nb_avis = parseInt(bulletMatch[1]);
                    }
                }

                // Strategy 3: parenthesized patterns
                if (!nb_avis) {
                    const parenMatch = fullText.match(/\((\d[\d\s]*)\s*avis\)/i) || fullText.match(/\((\d[\d\s]*)\)/);
                    if (parenMatch) nb_avis = parseInt(parenMatch[1].replace(/\s/g, ''));
                }

                // Strategy 4: aria-label on review button/element
                if (!nb_avis) {
                    const ariaEls = item.querySelectorAll('[aria-label]');
                    for (const el of ariaEls) {
                        const label = el.getAttribute('aria-label') || '';
                        const m = label.match(/(\d[\d\s]*)\s*avis/i) || label.match(/\((\d+)\)/);
                        if (m) { 
                            nb_avis = parseInt(m[1].replace(/\s/g, '')); 
                            if (nb_avis) break; 
                        }
                    }
                }

                results.push({
                    index: index, nom: titleEl.innerText, lien: linkEl.href,
                    rating: rating, nb_avis: nb_avis
                });
            });
            return results;
        }''')

        print(f"   [Maps] {len(list_data)} établissements trouvés. Extraction des détails...")

        count = 0
        for item in list_data:
            if count >= limit: break
            if item['nom'].lower() in seen_names: continue
            try:
                await page.goto(item["lien"], wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(2000)

                details = await page.evaluate(r'''() => {
                    const d = { site_web: "", telephone: "", adresse: "", rating: 0, nb_avis: 0, category: "", logo_url: "" };
                    
                    // ===== WEBSITE EXTRACTION (3 stratégies) =====
                    const anchors = document.querySelectorAll('a[href]');

                    // Stratégie 1 : data-item-id="website:..." (le plus fiable)
                    for (const a of anchors) {
                        const did = a.getAttribute('data-item-id') || '';
                        if (did.startsWith('website:') && a.href && !a.href.includes('google.') && !a.href.includes('maps.')) {
                            d.site_web = a.href; break;
                        }
                    }

                    // Stratégie 2 : texte du lien (FR + EN)
                    if (!d.site_web) {
                        for (const a of anchors) {
                            const txt = (a.innerText || a.getAttribute('aria-label') || '').toLowerCase().trim();
                            if ((txt.includes('site web') || txt.includes('site internet') || txt === 'website')
                                && a.href && !a.href.includes('google.') && !a.href.includes('maps.')) {
                                d.site_web = a.href; break;
                            }
                        }
                    }

                    // Stratégie 3 : aria-label contenant "website" (labels icônes)
                    if (!d.site_web) {
                        for (const a of anchors) {
                            const aria = (a.getAttribute('aria-label') || '').toLowerCase();
                            if (aria.includes('website') && a.href && !a.href.includes('google.') && !a.href.includes('maps.')) {
                                d.site_web = a.href; break;
                            }
                        }
                    }
                    
                    // ===== PHONE EXTRACTION =====
                    const telBtn = document.querySelector('button[data-item-id^="phone:tel:"]');
                    if (telBtn) d.telephone = telBtn.getAttribute('data-item-id').replace('phone:tel:', '');
                    else {
                        const telLink = document.querySelector('a[href^="tel:"]');
                        if (telLink) d.telephone = telLink.getAttribute('href').replace('tel:', '');
                    }
                    
                    // ===== ADDRESS EXTRACTION (improved robustness) =====
                    const addrEl = document.querySelector('button[data-item-id="address"]');
                    if (addrEl) {
                        d.adresse = (addrEl.innerText || '').trim();
                    } else {
                        // Fallback: search in aria-labels for address-like patterns
                        const addrPattern = Array.from(document.querySelectorAll('[aria-label]'))
                            .find(el => /\d+/.test(el.getAttribute('aria-label') || ''));
                        if (addrPattern) d.adresse = addrPattern.getAttribute('aria-label').trim();
                    }
                    
                    // ===== RATING EXTRACTION (improved) =====
                    // Strategy 1: Main rating element with F7nice class
                    let ratingEl = document.querySelector('div.F7nice span span[aria-hidden="true"]');
                    if (ratingEl) {
                        d.rating = parseFloat(ratingEl.innerText.replace(',', '.'));
                    }
                    // Strategy 2: aria-label with stars
                    if (!d.rating) {
                        const starAria = Array.from(document.querySelectorAll('[aria-label*="étoile"], [aria-label*="star"]'))
                            .find(el => /[\d.,]+\s*(étoile|star)/.test(el.getAttribute('aria-label') || ''));
                        if (starAria) {
                            const m = starAria.getAttribute('aria-label').match(/([\d.,]+)/);
                            if (m) d.rating = parseFloat(m[1].replace(',', '.'));
                        }
                    }
                    // Strategy 3: text node containing "sur 5"
                    if (!d.rating) {
                        const bodyText = document.body.innerText;
                        const ratingMatch = bodyText.match(/([\d.,]+)\s*sur\s*5/) || bodyText.match(/([\d.,]+)\s*★/);
                        if (ratingMatch) d.rating = parseFloat(ratingMatch[1].replace(',', '.'));
                    }
                    
                    // ===== REVIEW COUNT EXTRACTION (improved robustness) =====
                    const bodyText = document.body.innerText;
                    
                    // Strategy 1: Direct "X avis" pattern near the rating area (most reliable)
                    const ratingArea = document.querySelector('[aria-label*="étoile"], [aria-label*="star"], div.F7nice');
                    if (ratingArea && !d.nb_avis) {
                        const areaText = ratingArea.innerText || ratingArea.getAttribute('aria-label') || '';
                        const m = areaText.match(/(\d[\d\s]*)\s*avis/i);
                        if (m) d.nb_avis = parseInt(m[1].replace(/\s/g, ''));
                    }
                    
                    // Strategy 2: "X avis" pattern in full body (next most reliable)
                    if (!d.nb_avis) {
                        const avisMatch = bodyText.match(/(\d[\d\s]*)\s*avis/i) || bodyText.match(/(\d[\d\s]*)\s*évaluations?/i);
                        if (avisMatch) d.nb_avis = parseInt(avisMatch[1].replace(/\s/g, ''));
                    }
                    
                    // Strategy 3: parenthesized count
                    if (!d.nb_avis) {
                        const parenMatch = bodyText.match(/\((\d[\d\s]*)\s*avis\)/i) || bodyText.match(/\((\d+)\)/);
                        if (parenMatch) d.nb_avis = parseInt(parenMatch[1].replace(/\s/g, ''));
                    }
                    
                    // Strategy 4: "• X" bullet pattern (fragile, only last resort)
                    if (!d.nb_avis) {
                        const bulletMatch = bodyText.match(/[\u00b7\u2022]\s*(\d+)/);
                        if (bulletMatch) d.nb_avis = parseInt(bulletMatch[1]);
                    }
                    
                    // Strategy 5: Review button text
                    if (!d.nb_avis) {
                        const reviewBtn = document.querySelector('button[jsaction*="moreReviews"], button[jsaction*="review"]');
                        if (reviewBtn) {
                            const btnText = reviewBtn.innerText || reviewBtn.getAttribute('aria-label') || '';
                            const m = btnText.match(/(\d[\d\s]*)\s*avis/i) || btnText.match(/\((\d+)\)/);
                            if (m) d.nb_avis = parseInt(m[1].replace(/\s/g, ''));
                        }
                    }
                    
                    // ===== CATEGORY EXTRACTION =====
                    const catEl = document.querySelector('button[jsaction="pane.rating.category"]');
                    if (catEl) d.category = (catEl.innerText || '').trim();
                    
                    // ===== LOGO EXTRACTION (robust with multiple fallbacks) =====
                    // Strategy 1: img with "logo" in alt or class
                    let logoImg = document.querySelector('img[alt*="logo" i], img[class*="logo"]');
                    if (logoImg && logoImg.src) {
                        d.logo_url = logoImg.src;
                    }
                    
                    // Strategy 2: img with data-is-logo attribute
                    if (!d.logo_url) {
                        logoImg = document.querySelector('img[data-is-logo]');
                        if (logoImg && logoImg.src) d.logo_url = logoImg.src;
                    }
                    
                    // Strategy 3: header/banner image
                    if (!d.logo_url) {
                        logoImg = document.querySelector('[class*="header"] img:first-child, [class*="banner"] img:first-child, [class*="cover"] img:first-child');
                        if (logoImg && logoImg.src) d.logo_url = logoImg.src;
                    }
                    
                    // Strategy 4: large img near top of page (likely photo/logo)
                    if (!d.logo_url) {
                        const allImgs = Array.from(document.querySelectorAll('img'));
                        const topImg = allImgs.filter(img => {
                            const rect = img.getBoundingClientRect();
                            return rect.top < 300 && img.width > 50 && img.height > 50;
                        })[0];
                        if (topImg && topImg.src) d.logo_url = topImg.src;
                    }
                    
                    // Ensure logo_url is absolute
                    if (d.logo_url && !d.logo_url.startsWith('http')) {
                        if (d.logo_url.startsWith('/')) {
                            d.logo_url = window.location.origin + d.logo_url;
                        } else {
                            d.logo_url = window.location.origin + '/' + d.logo_url;
                        }
                    }

                    return d;
                }''')
                if not details.get('nb_avis'):
                    details['nb_avis'] = item.get('nb_avis', 0)
                if not details.get('rating') or details.get('rating') == 0:
                    details['rating'] = item.get('rating', 0)

                if not details.get('nb_avis'):
                    debug_snippet = details.get('_debug_text', '')[:200] if details.get('_debug_text') else ''
                    print(f"   [WARN] nb_avis=0 pour {item['nom'][:40]} (search={item.get('nb_avis',0)}, rating={details.get('rating',0)})")

                places.append({
                    'nom': item['nom'], 'site_web': details['site_web'],
                    'telephone': details['telephone'], 'adresse': details['adresse'],
                    'rating': details['rating'], 'nb_avis': details['nb_avis'],
                    'category': details['category'], 'logo_url': details['logo_url'],
                    'lien_maps': item['lien'], 'mot_cle': keyword, 'ville': city
                })
                seen_names.add(item['nom'].lower())
                count += 1
                status = "OK" if details['site_web'] else "--"
                print(f"   [{status}] {item['nom']} | {details['site_web'] or 'PAS DE SITE'} | {details['telephone'] or 'PAS DE TEL'}")
            except Exception as e:
                print(f"   [WARN] Erreur détails pour {item['nom']} : {e}")
    finally:
        try: await browser.close()
        except: pass
        try: await pw.stop()
        except: pass

    return places


# ===========================================================
# MAIN — Point d'entree
# ===========================================================

async def main_async(argv=None):
    import argparse
    import asyncio
    parser = argparse.ArgumentParser(description="Scraper Google Maps via Playwright")
    parser.add_argument("--keyword", required=True, help="Le metier (ex: 'restaurant')")
    parser.add_argument("--city", required=True, help="La ville (ex: 'Cotonou')")
    parser.add_argument("--limit", type=int, default=20, help="Nombre max de resultats (defaut: 20)")
    parser.add_argument("--min-emails", type=int, default=None, help="Nombre minimum de leads avec email requis")
    parser.add_argument("--campaign-id", type=int, default=None, help="ID de la campagne rattachée")
    parser.add_argument("--multi-zone", action="store_true", help="Utiliser l'agent de zones LLM")
    parser.add_argument("--offset", type=int, default=0, help="Nombre de résultats à ignorer")
    parser.add_argument("--min-reviews", type=int, default=0, help="Nombre minimum d'avis requis")
    parser.add_argument("--secteur", type=str, default="", help="Étiquette secteur (ex: immobilier)")
    parser.add_argument("--country", type=str, default="fr", help="Code pays (fr, bj, be, ch, lu)")
    parser.add_argument("--require-contact", action="store_true",
                        help="Ne garder que les leads avec téléphone OU email")
    parser.add_argument("--site-filter", choices=['all', 'with_site', 'without_site'], default='all',
                        help="Filtrer par présence de site web (défaut: all)")
    parser.add_argument("--max-passes", type=int, default=30,
                        help="Nombre maximum de passes de zones (défaut: 30)")
    parser.add_argument("--keyword-variants", action="store_true",
                        help="Générer des variantes de mots-clés via LLM")
    if argv is not None:
        args = parser.parse_args(argv)
    else:
        args = parser.parse_args()

    effective_limit = (args.limit - args.offset) if args.limit else (args.min_emails * 4 if args.min_emails else 80)
    
    print("=" * 60)
    print("Scraper Google Maps - Playwright Headless")
    print(f"   Recherche : {args.keyword} a {args.city}")
    print(f"   Limite : {effective_limit} resultats")
    print("=" * 60)

    start_time = time.time()
    MAX_PAR_PASSE    = 120
    MIN_EMAILS_CIBLE = args.min_emails

    try: get_config()
    except: pass

    date_scraping    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    valid_leads  = []
    emails_count = 0

    # Mémoire DB
    seen_noms_global = set()
    if _DB_AVAILABLE:
        try:
            with db_get_conn() as _conn:
                if args.secteur:
                    _rows = _conn.execute("SELECT LOWER(TRIM(nom)) FROM leads_bruts WHERE nom IS NOT NULL AND secteur=?", (args.secteur,)).fetchall()
                else:
                    _rows = _conn.execute("SELECT LOWER(TRIM(nom)) FROM leads_bruts WHERE nom IS NOT NULL").fetchall()
            seen_noms_global = set(r[0] for r in _rows if r[0])
            print(f"   [DB] Mémoire chargée : {len(seen_noms_global)} leads (secteur={args.secteur or 'tous'})")
        except: pass

    zones_queue = [args.city]
    zones_used  = set()

    if args.multi_zone:
        try:
            from scraper.zone_agent import get_city_subdivisions
            nb_zones = max(15, (effective_limit // MAX_PAR_PASSE) + 5)
            sous_zones = get_city_subdivisions(args.city, max_zones=nb_zones)
            zones_queue.extend(sous_zones)
        except:
            zones_queue += [f"{args.city} centre", f"{args.city} nord", f"{args.city} sud", f"{args.city} est", f"{args.city} ouest"]

    seen_z = set()
    zones_queue = [z for z in zones_queue if not (z.lower() in seen_z or seen_z.add(z.lower()))]

    # ── Variantes de mots-clés via LLM ──────────────────────────────
    keyword_list = [args.keyword]
    if args.keyword_variants:
        try:
            from scraper.keyword_variants import generate_keyword_variants
            keyword_list = generate_keyword_variants(args.keyword, args.city, args.country)
            print(f"   [VARIANTS] {len(keyword_list)} mots-clés : {keyword_list[:5]}")
        except Exception as e:
            print(f"   [VARIANTS] ⚠️ Erreur : {e} — Utilisation du mot-clé original")

    def _objectif_atteint() -> bool:
        if MIN_EMAILS_CIBLE: return emails_count >= MIN_EMAILS_CIBLE
        return len(valid_leads) >= effective_limit

    def _enrichir_place(place: dict):
        nom     = place.get("nom", "Inconnu")
        website = place.get("site_web")

        # Blacklist social media / annuaire / plateformes tierces
        if website:
            domain = extract_domain(website)
            blacklist = [
                # Réseaux sociaux
                "google.com", "facebook.com", "instagram.com", "twitter.com",
                "linkedin.com", "tiktok.com", "youtube.com", "snapchat.com",
                # Annuaires FR
                "pagesjaunes.fr", "societe.com", "infogreffe.fr", "pappers.fr",
                "verif.com", "manageo.fr", "annuaire-entreprises.data.gouv.fr",
                "tripadvisor", "yellowpages", "yandex.com", "yahoo.com",
                # Plateformes de commande / livraison
                "ubereats.com", "just-eat.fr", "justeat.fr", "deliveroo.com",
                "thefork.fr", "lafourchette.com", "lieux.atelier", "menudopme.fr",
                "5a resto", "five-a.fr", "foodchek.fr",
                # Avis / réputation
                "trustpilot.com", "reputation.com",
                # Menus / cartes
                "menus-solutions.com", "menuiserie.com", "menu.rest",
            ]
            if domain and any(bd in domain.lower() for bd in blacklist):
                place["site_web"] = None
                website = None

        return {
            'nom':          nom,
            'adresse':      place.get('adresse', ''),
            'site_web':     website or '',
            'telephone':    place.get('telephone', ''),
            'rating':       place.get('rating', ''),
            'nb_avis':      int(place.get('nb_avis') or 0),
            'logo_url':     place.get('logo_url', ''),
            'email':        '',
            'statut_email': '',
            'email_source': '',
            'date_scraping': date_scraping,
            'mot_cle':      args.keyword,
            'ville':        args.city,
            'category':     place.get('category', ''),
            'lien_maps':    place.get('lien_maps', ''),
            'campaign_id':  args.campaign_id,
            'pays':         args.country,
        }

    passe_num = 0
    empty_streak = 0
    keyword_index = 0
    current_keyword = keyword_list[0] if keyword_list else args.keyword
    _STOP_FLAG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'maps_stop.flag')

    while zones_queue and not _objectif_atteint() and passe_num < args.max_passes:
        if os.path.exists(_STOP_FLAG):
            try: os.remove(_STOP_FLAG)
            except: pass
            print("\n   [STOP] Arrêt demandé depuis le dashboard.")
            break

        zone = zones_queue.pop(0)
        if zone.lower() in zones_used: continue
        zones_used.add(zone.lower())
        passe_num += 1

        # Taille de la requête pour cette zone
        if MIN_EMAILS_CIBLE:
            manquants  = MIN_EMAILS_CIBLE - emails_count
            limit_zone = min(MAX_PAR_PASSE, max(manquants * 5, 20))
        else:
            limit_zone = min(MAX_PAR_PASSE, effective_limit - len(valid_leads))

        print(f"\n{'='*60}")
        print(f"Passe {passe_num}/{args.max_passes} : {current_keyword} @ {zone}")
        if MIN_EMAILS_CIBLE:
            print(f"   Emails trouvés : {emails_count}/{MIN_EMAILS_CIBLE}")
        else:
            print(f"   Leads collectés : {len(valid_leads)}/{effective_limit}")
        print(f"{'='*60}")

        try:
            batch_places = await scrape_google_maps(current_keyword, zone, limit_zone,
                                                     known_names=seen_noms_global,
                                                     country=args.country)
            if not batch_places:
                empty_streak += 1
                print(f"   [WARN] Aucun résultat pour '{zone}'. (streak: {empty_streak}/3)")
                if empty_streak >= 3:
                    print(f"\n   [STOP] 3 zones vides consécutives → arrêt.")
                    break
                continue

            # Reset du streak si on trouve quelque chose
            empty_streak = 0

            # Déduplication
            nouveaux = [p for p in batch_places
                        if p.get('nom', '').strip().lower() not in seen_noms_global
                        and not seen_noms_global.add(p.get('nom', '').strip().lower())]

            print(f"   -> {len(nouveaux)} nouveaux lieux (sur {len(batch_places)} trouvés)")

            for place in nouveaux:
                if _objectif_atteint():
                    print(f"\n   [OK] Objectif atteint → arrêt immédiat.")
                    break

                # Filtre min-reviews
                if args.min_reviews > 0 and (place.get('nb_avis') or 0) < args.min_reviews:
                    continue

                lead = await asyncio.to_thread(_enrichir_place, place)
                if lead is None:
                    continue

                # Filtre site web
                if args.site_filter == 'without_site' and lead.get('site_web'):
                    continue
                elif args.site_filter == 'with_site' and not lead.get('site_web'):
                    continue

                # Propager secteur et pays
                if args.secteur:
                    lead['secteur'] = args.secteur
                lead['pays'] = args.country

                # Filtre : avec téléphone OU email si --require-contact
                if args.require_contact and not lead.get('telephone') and not lead.get('email'):
                    continue

                if lead['email']:
                    emails_count += 1

                valid_leads.append(lead)

                # SQLite immédiat
                if _DB_AVAILABLE:
                    try:
                        db_insert_lead(lead)
                    except Exception as e:
                        logger.error(f"SQLite insert_lead({lead['nom']}): {e}")

                if MIN_EMAILS_CIBLE:
                    print(f"   [PROGRESSION] emails={emails_count}/{MIN_EMAILS_CIBLE}  leads={len(valid_leads)}")
                else:
                    print(f"   [PROGRESSION] leads={len(valid_leads)}/{effective_limit}")

                # Direct campaign tracker update
                if args.campaign_id:
                    try:
                        from services.campaign_tracker import update_progress
                        update_progress(
                            args.campaign_id,
                            processed=len(valid_leads),
                            total=effective_limit,
                            emails_found=emails_count,
                            phase='scraping',
                        )
                    except Exception:
                        pass

        except Exception as e:
            print(f"   [ERREUR] Scraping zone '{zone}' : {e}")
            empty_streak += 1
            await asyncio.sleep(3)

        # Si zones_queue est vide et objectif pas atteint : essayer la variante suivante
        if not zones_queue and not _objectif_atteint() and len(keyword_list) > 1:
            keyword_index = (keyword_index + 1) % len(keyword_list)
            if keyword_index != 0:
                current_keyword = keyword_list[keyword_index]
                print(f"\n   [ROTATION] Nouveau mot-clé : '{current_keyword}'")
                # Réinitialiser les zones pour le nouveau mot-clé
                zones_queue = [args.city]
                if args.multi_zone:
                    try:
                        from scraper.zone_agent import get_city_subdivisions
                        sous_zones = get_city_subdivisions(args.city, max_zones=10)
                        zones_queue.extend(sous_zones)
                    except:
                        pass

        # Fallback zones (uniquement hors multi-zone)
        if not zones_queue and not _objectif_atteint() and not args.multi_zone:
            _fallbacks = [
                f"{args.city} centre", f"{args.city} nord", f"{args.city} sud",
                f"{args.city} est", f"{args.city} ouest",
            ]
            _new_zones = [z for z in _fallbacks if z.lower() not in zones_used]
            if _new_zones:
                print(f"\n   [AUTO-ZONE] Ajout de {len(_new_zones)} zones de repli...")
                zones_queue.extend(_new_zones)

        await asyncio.sleep(2)

    # Résumé final
    elapsed = time.time() - start_time
    process = psutil.Process(os.getpid())
    mem_mb = process.memory_info().rss / (1024 * 1024)

    print("\n" + "=" * 60)
    print(f"Scraping terminé en {elapsed:.1f}s")
    print(f"   Total leads      : {len(valid_leads)}")
    print(f"   Avec email       : {emails_count}")
    print(f"   RAM utilisée     : {mem_mb:.1f} Mo")
    print("=" * 60)

    # Browser headless propre — le finally dans scrape_google_maps ferme chaque instance

if __name__ == "__main__":
    import asyncio
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n[!] Interruption par l'utilisateur.")
    except Exception as e:
        print(f"\n[!] Erreur fatale : {e}")


