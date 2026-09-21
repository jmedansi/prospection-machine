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


def _resolve_liste_cible(campagne_id, liste_arg, secteur=None, mot_cle=None):
    """Résout la liste cible (id ou nom exact) dans une campagne.

    Sans liste précisée : crée (ou réutilise le même jour) une LISTE DÉDIÉE au
    scraping, nom générique compréhensible « Scrap <secteur/mot-clé> — <date> ».
    Retourne la liste_id, ou None → la campagne utilisera sa liste par défaut.
    """
    if not liste_arg:
        from datetime import date
        base = (secteur or mot_cle or 'leads').strip()
        if len(base) > 40:
            base = base[:40].rstrip()
        s = f"Scrap {base} — {date.today().isoformat()}"
    else:
        s = str(liste_arg).strip()
    from database import listes as listes_repo
    if s.isdigit():
        try:
            liste = listes_repo.get_liste(int(s))
        except Exception:
            liste = None
        if liste and liste.get('campagne_id') == campagne_id:
            return liste['id']
    for l_row in listes_repo.list_listes(campagne_id=campagne_id, search=s):
        if (l_row.get('nom') or '').strip().lower() == s.lower():
            return l_row['id']
    res = listes_repo.create_liste(campagne_id=campagne_id, nom=s, source='scraping',
                                   secteur=secteur or '')
    if res.get('success'):
        return res['liste']['id']
    return None

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

        # ── Bypass consent Google (redirection consent.google.com) ────────
        # Sans ce contournement, chaque scrap retombe sur la page de consentement
        # et ne collecte AUCUN résultat. On accepte les cookies puis on relance.
        for _ in range(3):
            if "consent.google.com" in page.url:
                print("   [Maps] Consentement détecté, acceptation…")
                accepted = False
                try:
                    await page.get_by_role("button", name="Tout accepter").first.click(timeout=6000)
                    accepted = True
                except Exception:
                    try:
                        await page.click('button[data-testid]:not([data-testid=""]):text-is("Tout accepter")', timeout=4000)
                        accepted = True
                    except Exception:
                        pass
                if not accepted:
                    try:
                        await page.evaluate("""() => { const b=[...document.querySelectorAll('button')].find(x=>(x.innerText||'').includes('Tout accepter')); if(b)b.click(); }""")
                        accepted = True
                    except Exception:
                        pass
                await page.wait_for_timeout(4000)
                if "consent.google.com" not in page.url:
                    break
            else:
                break
        await page.wait_for_timeout(2000)

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

                // ===== RATING + NB_AVIS depuis span.ZkP5Je (aria-label="X,X étoiles Y avis") =====
                // C'est la source la plus fiable sur Google Maps FR (format 2024-2026)
                const zkP5Je = item.querySelector('span.ZkP5Je');
                if (zkP5Je) {
                    const label = zkP5Je.getAttribute('aria-label') || '';
                    // "4,9\xa0étoiles 32\xa0avis"
                    const starM = label.match(/([\d][\d,\.]+)/);
                    if (starM) rating = parseFloat(starM[1].replace(',', '.'));
                    const avisM = label.match(/([\d][\d\s\xa0]*)\s*avis/i);
                    if (avisM) nb_avis = parseInt(avisM[1].replace(/[\s\xa0]/g, ''));
                }

                // Fallback rating: span.MW4etd (juste le chiffre de la note)
                if (!rating) {
                    const mw4 = item.querySelector('span.MW4etd');
                    if (mw4) {
                        const m = (mw4.innerText || '').match(/([\d.,]+)/);
                        if (m) rating = parseFloat(m[1].replace(',', '.'));
                    }
                }

                // Fallback nb_avis: span.UY7F9 → contient "(32)" entre parenthèses
                if (!nb_avis) {
                    const uy7f9 = item.querySelector('span.UY7F9');
                    if (uy7f9) {
                        const m = (uy7f9.innerText || '').match(/\(([\d\s\xa0]+)\)/);
                        if (m) nb_avis = parseInt(m[1].replace(/[\s\xa0]/g, ''));
                    }
                }

                // Fallback nb_avis: depuis l'innerText de l'item (patterns variés)
                if (!nb_avis) {
                    const itemText = item.innerText || '';
                    // Pattern: "(183)" standalone
                    const parenM = itemText.match(/\(([\d][\d\s\xa0]*)\)/);
                    if (parenM) nb_avis = parseInt(parenM[1].replace(/[\s\xa0]/g, ''));
                }

                // Fallback nb_avis: aria-label sur d'autres éléments
                if (!nb_avis) {
                    const ariaEls = item.querySelectorAll('[aria-label*="avis"]');
                    for (const el of ariaEls) {
                        const label = el.getAttribute('aria-label') || '';
                        const m = label.match(/([\d][\d\s\xa0]*)\s*avis/i);
                        if (m) { nb_avis = parseInt(m[1].replace(/[\s\xa0]/g, '')); if (nb_avis) break; }
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
                    
                    // ===== WEBSITE EXTRACTION (Google Maps authority & aria) =====
                    // 1. data-item-id="authority" ou data-item-id="website:..."
                    const authA = document.querySelector('a[data-item-id="authority"], a[data-item-id^="website:"]');
                    if (authA && authA.href && !authA.href.includes('google.') && !authA.href.includes('maps.')) {
                        d.site_web = authA.href;
                    }
                    
                    // 2. aria-label ou texte contenant "site Web" / "website"
                    if (!d.site_web) {
                        const anchors = Array.from(document.querySelectorAll('a[href]'));
                        for (const a of anchors) {
                            const aria = (a.getAttribute('aria-label') || '').toLowerCase();
                            const txt = (a.innerText || '').toLowerCase().trim();
                            if ((aria.includes('site web') || aria.includes('website') || txt.includes('site web') || txt === 'website')
                                && a.href && !a.href.includes('google.') && !a.href.includes('maps.')) {
                                d.site_web = a.href;
                                break;
                            }
                        }
                    }
                    
                    // ===== PHONE EXTRACTION =====
                    const telBtn = document.querySelector('[data-item-id^="phone:tel:"]');
                    if (telBtn) {
                        const did = telBtn.getAttribute('data-item-id') || '';
                        d.telephone = did.replace('phone:tel:', '').trim();
                    }
                    if (!d.telephone) {
                        const telLink = document.querySelector('a[href^="tel:"]');
                        if (telLink) d.telephone = telLink.getAttribute('href').replace('tel:', '').trim();
                    }
                    if (!d.telephone) {
                        const telAria = document.querySelector('[aria-label*="téléphone" i], [aria-label*="telephone" i]');
                        if (telAria) {
                            const tm = (telAria.getAttribute('aria-label') || '').match(/(\+?\d[\d\s\.\-]{8,})/);
                            if (tm) d.telephone = tm[1].trim();
                        }
                    }
                    
                    // ===== ADDRESS EXTRACTION =====
                    const addrEl = document.querySelector('[data-item-id="address"]');
                    if (addrEl) {
                        d.adresse = (addrEl.innerText || addrEl.getAttribute('aria-label') || '')
                            .replace(/^Adresse:\s*/i, '')
                            .replace(/^[\ue000-\uf8ff\s\n]+/, '')
                            .trim();
                    } else {
                        const addrAria = document.querySelector('[aria-label^="Adresse:"]');
                        if (addrAria) {
                            d.adresse = (addrAria.getAttribute('aria-label') || '')
                                .replace(/^Adresse:\s*/i, '')
                                .replace(/^[\ue000-\uf8ff\s\n]+/, '')
                                .trim();
                        }
                    }
                    
                    // ===== RATING EXTRACTION =====
                    const rEl = document.querySelector('div.F7nice span[aria-hidden="true"], span.ceNzKf');
                    if (rEl) {
                        const rm = rEl.innerText.match(/([\d.,]+)/);
                        if (rm) d.rating = parseFloat(rm[1].replace(',', '.'));
                    }
                    if (!d.rating) {
                        const starAria = Array.from(document.querySelectorAll('[aria-label*="étoile"], [aria-label*="star"], [aria-label*="stars"]'))
                            .find(el => /[\d.,]+\s*(étoile|star)/i.test(el.getAttribute('aria-label') || ''));
                        if (starAria) {
                            const sm = starAria.getAttribute('aria-label').match(/([\d.,]+)/);
                            if (sm) d.rating = parseFloat(sm[1].replace(',', '.'));
                        }
                    }
                    
                    // ===== REVIEW COUNT EXTRACTION (fiche détail) =====
                    // Stratégie 1: span.ZkP5Je (même classe que dans la liste)
                    const zkDetail = document.querySelector('span.ZkP5Je');
                    if (zkDetail) {
                        const label = zkDetail.getAttribute('aria-label') || '';
                        const am = label.match(/([\d][\d\s\xa0]*)\s*avis/i);
                        if (am) d.nb_avis = parseInt(am[1].replace(/[\s\xa0]/g, ''));
                        if (!d.rating) {
                            const sm = label.match(/([\d][\d,\.]+)/);
                            if (sm) d.rating = parseFloat(sm[1].replace(',', '.'));
                        }
                    }
                    // Stratégie 2: span.UY7F9 → "(32)"
                    if (!d.nb_avis) {
                        const uy7f9 = document.querySelector('span.UY7F9');
                        if (uy7f9) {
                            const m = (uy7f9.innerText || '').match(/\(([\d\s\xa0]+)\)/);
                            if (m) d.nb_avis = parseInt(m[1].replace(/[\s\xa0]/g, ''));
                        }
                    }
                    // Stratégie 3: button ou span aria-label "X avis"
                    if (!d.nb_avis) {
                        const avisEls = Array.from(document.querySelectorAll('[aria-label*="avis" i], button[jsaction*="moreReviews"]'));
                        for (const el of avisEls) {
                            const raw = el.getAttribute('aria-label') || el.innerText || '';
                            const am = raw.match(/([\d][\d\s\xa0]*)\s*avis/i) || raw.match(/\(([\d\s\xa0]+)\)/);
                            if (am) { d.nb_avis = parseInt(am[1].replace(/[\s\xa0]/g, '')); if (d.nb_avis) break; }
                        }
                    }
                    // Stratégie 4: scan global du texte principal
                    if (!d.nb_avis) {
                        const mainEl = document.querySelector('div[role="main"]');
                        if (mainEl) {
                            const hm = mainEl.innerText.match(/\(([\d][\d\s\xa0]*)\)/) || mainEl.innerText.match(/([\d][\d\s\xa0]*)\s*avis/i);
                            if (hm) d.nb_avis = parseInt(hm[1].replace(/[\s\xa0]/g, ''));
                        }
                    }
                    
                    // ===== CATEGORY EXTRACTION =====
                    const catEl = document.querySelector('button[jsaction*="pane.rating.category"], button[jsaction*="category"], button.DkEaL');
                    if (catEl) d.category = (catEl.innerText || '').trim();
                    
                    // ===== DIRECT EMAIL ON GOOGLE MAPS =====
                    d.email = "";
                    const mailtoA = document.querySelector('a[href^="mailto:"]');
                    if (mailtoA) {
                        const raw = (mailtoA.getAttribute('href') || '').replace(/^mailto:/i, '').split('?')[0].trim();
                        if (raw && !raw.includes('google.') && !raw.includes('sentry.')) d.email = raw;
                    }

                    // ===== LOGO / PHOTO EXTRACTION =====
                    let logoImg = document.querySelector('img[alt*="logo" i], img[class*="logo"]');
                    if (!logoImg) logoImg = document.querySelector('button[jsaction*="pane.heroHeaderImage"] img, div[role="main"] img');
                    if (logoImg && logoImg.src && !logoImg.src.startsWith('data:')) {
                        d.logo_url = logoImg.src;
                    }
                    
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
                    'lien_maps': item['lien'], 'mot_cle': keyword, 'ville': city,
                    'email': details.get('email', '')
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
    parser.add_argument("--objectif", type=str, default="",
                        help="Campagne v2 (nom ou id) dans laquelle ranger les leads collectés "
                             "(ex: « Refonte site web »). Créée si elle n'existe pas. "
                             "Compat : l'ancien terme « objectif ».")
    parser.add_argument("--liste", type=str, default="",
                        help="Liste cible (nom ou id) DANS la campagne --objectif ; défaut = "
                             "liste par défaut de la campagne (auto-créée).")
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
    MIN_EMAILS_CIBLE = args.min_emails if (args.min_emails and args.min_emails > 0) else None

    try: get_config()
    except: pass

    date_scraping    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    valid_leads  = []
    emails_count = 0

    # ── Campagne v2 cible (résolue UNE fois avant le premier lead) ───────────
    v2_campagne = None
    v2_liste = None
    v2_counters = {'importes': 0, 'doublons': 0, 'supprimes': 0}
    if args.objectif:
        try:
            from core.objectif_registry import resolve_or_create_campagne, get_or_create_liste
            from database import listes as listes_repo
            v2_campagne = resolve_or_create_campagne(args.objectif)
            print(f"   [V2] Campagne cible : #{v2_campagne[0]} « {v2_campagne[1]} »" if v2_campagne
                  else f"   [V2] ⚠️ Impossible de rattacher la campagne « {args.objectif} »")
            if v2_campagne:
                v2_liste = _resolve_liste_cible(v2_campagne[0], args.liste,
                                                secteur=args.secteur, mot_cle=args.keyword)
        except Exception as e:
            print(f"   [V2] ⚠️ Échec résolution campagne « {args.objectif} » : {e}")
            v2_campagne = None

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
        social_url = None

        # Détection des réseaux sociaux vs site web propre
        if website:
            domain = extract_domain(website) or ""
            social_domains = ["facebook.com", "instagram.com", "linkedin.com", "tiktok.com", "twitter.com", "x.com"]
            if any(sd in domain.lower() for sd in social_domains):
                social_url = website
                place["site_web"] = None
                website = None

            blacklist = [
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
            if website and any(bd in domain.lower() for bd in blacklist):
                place["site_web"] = None
                website = None

        found_emails = []
        # 1. Email extrait directement sur la fiche Maps (si disponible)
        if place.get("email"):
            found_emails.append(place["email"].strip())

        email = ""
        email_2 = ""
        statut_email = ""
        email_source = ""
        tel = place.get("telephone", "") or ""

        # 2. Recherche email approfondie sur le site web si disponible
        if website and _EMAIL_FINDER_AVAILABLE:
            try:
                res_email = find_email_all_methods(website, verbose=False, fast_mode=True)
                if res_email and res_email.get("email"):
                    for e in res_email["email"].split(","):
                        e_clean = e.strip()
                        if e_clean:
                            found_emails.append(e_clean)
                    email_source = res_email.get("source", "site_web")
            except Exception as e:
                logger.error(f"Erreur email_finder pour {nom} ({website}): {e}")

        # 3. Filtrage des emails tiers, jetables ou parasites + déduplication
        try:
            from core.email_constants import is_excluded, score_email
        except ImportError:
            def is_excluded(x): return False
            def score_email(x): return 99

        valid_emails = []
        for em in found_emails:
            em_clean = em.strip()
            if em_clean and '@' in em_clean and not is_excluded(em_clean):
                if em_clean.lower() not in [v.lower() for v in valid_emails]:
                    valid_emails.append(em_clean)

        # 4. Tri par pertinence (contact@, direction@, etc.) & attribution email / email_2
        if valid_emails:
            valid_emails.sort(key=lambda x: score_email(x))
            email = valid_emails[0]
            email_2 = ", ".join(valid_emails[1:]) if len(valid_emails) > 1 else ""
            statut_email = "Valide"
            if not email_source:
                email_source = "maps" if place.get("email") else "site_web"

        # Recherche téléphone sur le site web si manquant
        if website and not tel:
            try:
                tel_trouve = search_phone_on_website(website, country=args.country)
                if tel_trouve:
                    tel = tel_trouve
            except Exception as e:
                logger.error(f"Erreur search_phone pour {nom} ({website}): {e}")

        return {
            'nom':          nom,
            'adresse':      place.get('adresse', ''),
            'site_web':     website or '',
            'telephone':    tel,
            'rating':       place.get('rating', ''),
            'nb_avis':      int(place.get('nb_avis') or 0),
            'logo_url':     place.get('logo_url', ''),
            'email':        email,
            'email_2':      email_2,
            'statut_email': statut_email,
            'email_source': email_source,
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

                # Miroir v2 : insertion du lead enrichi DANS la liste cible (ou liste par défaut)
                if v2_campagne:
                    try:
                        from core.objectif_registry import import_lead_as_prospect
                        r = import_lead_as_prospect(
                            v2_campagne[0], lead,
                            source='scraping',
                            data_extra_extra={'campaign_id': args.campaign_id},
                            liste_id=v2_liste,
                        )
                        if r.get('statut_dedupe') == 'created':
                            v2_counters['importes'] += 1
                        elif r.get('statut_dedupe') == 'updated':
                            v2_counters['importes'] += 1
                            print(f"   [V2] {lead['nom']} enrichi (déjà en base, autre campagne)")
                        elif r.get('statut_dedupe') == 'doublon':
                            v2_counters['doublons'] += 1
                        elif r.get('statut_dedupe') == 'suppression_list':
                            v2_counters['supprimes'] += 1
                            print(f"   [V2] {lead['nom']} ignoré (désinscrit)")
                    except Exception as e:
                        logger.error(f"V2 insert prospect({lead['nom']}): {e}")

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
                            phase_detail=f"{lead.get('nom', '')} ({len(valid_leads)}/{effective_limit})",
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
    if v2_campagne:
        _liste_nom = ""
        if v2_liste:
            try:
                from database import listes as _lr
                _liste_nom = ( _lr.get_liste(v2_liste) or {} ).get('nom', '')
            except Exception:
                _liste_nom = ""
        print(f"   [V2] Campagne     : #{v2_campagne[0]} « {v2_campagne[1]} »"
              f"  (liste: #{v2_liste or 'défaut'} {_liste_nom})")
        print(f"   [V2] Importés     : {v2_counters['importes']}  (doublons: {v2_counters['doublons']}, désinscrits: {v2_counters['supprimes']})")
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


