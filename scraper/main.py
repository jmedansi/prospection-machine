# -*- coding: utf-8 -*-
"""
Scraper Google Maps via Playwright headless + stealth.
Extrait les établissements locaux et écrit dans Google Sheets (leads_bruts).
Zéro dépendance Gemini — 100% Python + outils spécialisés.
"""
import sys
import os
import argparse
import asyncio

# Forcer l'encodage UTF-8 pour la sortie standard (Windows support)
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
import logging
import re
import time
import random
from datetime import datetime
from urllib.parse import quote, urlparse

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
    elif source == 'hunter_api':
        base = 90
    elif source == 'smtp_guess':
        base = 60
    elif source == 'homepage_basic':
        base = 50
    else:
        base = 40
    # Bonus selon la priorité de l'alias (contact@ > info@ > …)
    bonus = max(0, 10 - priority)
    return min(100, base + bonus)


def extract_domain(url):
    """Extrait le domaine d'une URL."""
    if not url:
        return None
    try:
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url
        parsed = urlparse(url)
        domain = parsed.netloc
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain
    except Exception as e:
        logger.error(f"Erreur extraction domaine depuis {url}: {e}")
        return None


def search_email_hunter(domain, api_key):
    """Cherche un email pour le domaine via Hunter.io."""
    url = "https://api.hunter.io/v2/domain-search"
    params = {"domain": domain, "api_key": api_key}
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        emails = data.get('data', {}).get('emails', [])
        if emails:
            return emails[0].get('value')
        return None
    except Exception as e:
        logger.error(f"Erreur Hunter.io pour {domain}: {e}")
        return None


def search_phone_on_website(url):
    """Cherche un numero de telephone sur une page web s'il est manquant sur Google Maps."""
    if not url:
        return None
    try:
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        
        # Regex basique pour trouver des numéros français ou internationaux communs
        tels_trouves = re.findall(r'(?:(?:\+|00)33[\s.-]{0,3}(?:\(0\)[\s.-]{0,3})?|0)[1-9](?:(?:[\s.-]?\d{2}){4}|\d{2}(?:[\s.-]?\d{3}){2})', response.text)
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




# ===========================================================
# GEMINI — Extraction Google Maps
# ===========================================================

def scrape_google_maps(keyword, city, limit=20, known_names=None):
    """
    Scrape Google Maps via Gemini (Search Grounding).
    Remplace l'ancienne approche Playwright qui était trop lourde.
    """
    from google import genai
    from google.genai import types
    import json
    
    places = []
    seen_names = set(known_names) if known_names else set()
    
    print(f"\n[Gemini Maps] Ouverture de la recherche : {keyword} à {city}")
    
    config = get_config()
    api_key = config.get("google_api_key")
    if not api_key:
        print("   [ERREUR] Aucune clé google_api_key (Gemini) trouvée. Ajoute là dans config_comptes.")
        return places
        
    client = genai.Client(api_key=api_key)
    
    prompt = f"Effectue une recherche sur Google intégrant Google Maps pour trouver {limit} '{keyword}' à '{city}'. " \
             f"Retourne les résultats STRICTEMENT au format JSON : une liste d'objets. Chaque objet DOIT contenir les clés " \
             f" exactes suivantes: 'nom', 'rating' (float), 'nb_avis' (entier), 'adresse', 'telephone', 'site_web', 'category', 'lien_maps'. " \
             f"Cherche de vrais professionnels locaux et retourne leurs vraies données. Limite-toi à {limit} résultats maximum."
             
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash-lite',
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[{"google_search": {}}],
                response_mime_type="application/json",
                temperature=0.1
            )
        )
        
        try:
            results = json.loads(response.text)
        except Exception as e:
            print(f"   [ERREUR] Erreur de parsing JSON de la réponse Gemini: {e}")
            logger.error(f"Gemini output parsing failed: {response.text}")
            return places
            
        if not isinstance(results, list):
            results = [results]
            
        print(f"\n   [OK] {len(results)} fiches extraites par Gemini")
        
        for details in results:
            if not isinstance(details, dict): continue
            
            nom = details.get("nom")
            if not nom: continue
            
            nom_clean = nom.strip()
            if nom_clean.lower() not in seen_names:
                seen_names.add(nom_clean.lower())
                
                try: details["rating"] = float(details.get("rating") or 0)
                except: details["rating"] = 0.0
                
                try: details["nb_avis"] = int(details.get("nb_avis") or 0)
                except: details["nb_avis"] = 0
                
                details["nom"] = nom_clean
                details["mot_cle"] = keyword
                details["ville"] = city
                
                places.append(details)
                
                site = details.get("site_web")
                rating = details.get("rating", "?")
                nb_avis = details.get("nb_avis", 0)
                status = f"OK] {nom_clean} | {site}" if site else f"--] {nom_clean} | PAS DE SITE"
                print(f"   [{status} | {rating}/5 | {nb_avis} avis")
                
    except Exception as e:
        logger.error(f"Erreur globale Gemini Maps: {e}")
        print(f"   [ERREUR] Erreur globale Gemini : {e}")

    return places


            # 4. Recuperer les liens de toutes les fiches
            links = await feed.query_selector_all('a.hfpxzc')
            if not links:
                links = await feed.query_selector_all('a[href*="/maps/place/"]')
            
            place_urls = []
            for link in links:
                href = await link.get_attribute('href')
                if href and "/maps/place/" in href:
                    place_urls.append(href)
            
            total = min(len(place_urls), limit)
            print(f"\n   [OK] {total} fiches a extraire (sur {len(place_urls)} trouvees)")

            # 5. Extraction parallèle des fiches
            semaphore = asyncio.Semaphore(3)  # Max 3 workers en parallèle

            async def process_url(url, idx):
                async with semaphore:
                    # Créer une nouvelle page pour chaque worker afin d'éviter les conflits de navigation
                    # mais réutiliser le même contexte pour garder les cookies/session
                    new_page = await context.new_page()
                    await new_page.route("**/*", block_resources)
                    
                    try:
                        print(f"   [Worker {idx+1}] Navigation vers : {url[:50]}...")
                        # Utiliser wait_until="commit" ou "domcontentloaded" pour plus de vitesse
                        await new_page.goto(url, wait_until="domcontentloaded", timeout=60000)
                        await new_page.wait_for_timeout(2000)
                        
                        details = await extract_place_details(new_page)
                        if details and details.get("nom"):
                            details["mot_cle"] = keyword
                            details["ville"] = city
                            return details
                        return None
                    except Exception as e:
                        logger.error(f"Erreur worker {idx+1} pour {url}: {e}")
                        return None
                    finally:
                        await new_page.close()

            tasks = [process_url(url, i) for i, url in enumerate(place_urls[:limit])]
            results = await asyncio.gather(*tasks)

            for details in results:
                if details and details.get("nom"):
                    nom = details["nom"]
                    if nom not in seen_names:
                        seen_names.add(nom)
                        places.append(details)
                        
                        site = details.get("site_web")
                        rating = details.get("rating", "?")
                        nb_avis = details.get("nb_avis", 0)
                        status = f"OK] {nom} | {site}" if site else f"--] {nom} | PAS DE SITE"
                        print(f"   [{status} | {rating}/5 | {nb_avis} avis")

        except Exception as e:
            logger.error(f"Erreur globale scraping: {e}")
            print(f"   [ERREUR] Erreur globale : {e}")

        finally:
            # Fermeture propre du navigateur
            await browser.close()
            print(f"\n   [OK] Navigateur ferme proprement.")

    return places


# ===========================================================
# MAIN — Point d'entree
# ===========================================================

def main():
    parser = argparse.ArgumentParser(description="Scraper Google Maps via Playwright")
    parser.add_argument("--keyword", required=True, help="Le metier (ex: 'restaurant')")
    parser.add_argument("--city", required=True, help="La ville (ex: 'Cotonou')")
    parser.add_argument("--limit", type=int, default=20, help="Nombre max de resultats (defaut: 20)")
    parser.add_argument("--min-emails", type=int, default=None, help="Nombre minimum de leads avec email requis. Le scraper continue jusqu'à trouver ce nombre")
    parser.add_argument("--campaign-id", type=int, default=None, help="ID de la campagne rattachée")
    parser.add_argument("--multi-zone", action="store_true", help="Utiliser l'agent de zones pour explorer les quartiers")
    args = parser.parse_args()

    # Quand min_emails est spécifié, effective_limit n'est pas une limite dure :
    # le scraper continue jusqu'à trouver min_emails emails, peu importe le nombre
    # de leads à inspecter. effective_limit sert uniquement de taille par zone.
    effective_limit = args.limit if args.limit else (args.min_emails * 4 if args.min_emails else 80)
    
    print("=" * 60)
    print("Scraper Google Maps - Playwright Headless")
    print(f"   Recherche : {args.keyword} a {args.city}")
    print(f"   Limite : {effective_limit} resultats")
    if args.min_emails:
        print(f"   Objectif emails : {args.min_emails} minimum")
    print("=" * 60)

    start_time = time.time()

    # ================================================================
    # CONFIG GLOBALE DE LA SESSION
    # ================================================================
    MAX_PAR_PASSE    = 120
    MIN_EMAILS_CIBLE = args.min_emails  # None si non spécifié

    # Config API (clés Hunter, etc.)
    try:
        get_config()
    except Exception as e:
        print(f"   [WARN] Config non chargee : {e}")

    date_scraping    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    valid_leads  = []
    emails_count = 0

    # Mémoire DB : charger les noms déjà connus pour ne pas re-scraper ni re-enrichir
    if _DB_AVAILABLE:
        try:
            with db_get_conn() as _conn:
                _rows = _conn.execute(
                    "SELECT LOWER(TRIM(nom)) FROM leads_bruts WHERE nom IS NOT NULL AND nom != ''"
                ).fetchall()
            seen_noms_global = set(r[0] for r in _rows if r[0])
            print(f"   [DB] Mémoire chargée : {len(seen_noms_global)} leads déjà connus (seront ignorés).")
        except Exception as _e:
            seen_noms_global = set()
            print(f"   [WARN] Mémoire DB non chargée : {_e}")
    else:
        seen_noms_global = set()

    # ================================================================
    # Construction de la file de zones à explorer
    # ================================================================
    zones_queue = [args.city]
    zones_used  = set()

    if args.multi_zone:
        try:
            from scraper.zone_agent import get_city_subdivisions
        except ImportError:
            try:
                from zone_agent import get_city_subdivisions
            except ImportError:
                get_city_subdivisions = None

        if get_city_subdivisions:
            print(f"\n[ZoneAgent] Découverte des sous-zones de '{args.city}'...")
            nb_zones   = max(15, (effective_limit // MAX_PAR_PASSE) + 5)
            sous_zones = get_city_subdivisions(args.city, max_zones=nb_zones)
            zones_queue.extend(sous_zones)
            print(f"[ZoneAgent] {len(sous_zones)} zones disponibles.")
        else:
            print("   [WARN] ZoneAgent non disponible. Variantes génériques utilisées.")
            zones_queue += [
                f"{args.city} centre", f"{args.city} nord",
                f"{args.city} sud",    f"{args.city} est", f"{args.city} ouest",
            ]

    # Dédupliquer la file tout en préservant l'ordre
    seen_z = set()
    zones_queue = [z for z in zones_queue
                   if not (z.lower() in seen_z or seen_z.add(z.lower()))]

    # ================================================================
    # HELPERS
    # ================================================================
    def _objectif_atteint() -> bool:
        if MIN_EMAILS_CIBLE:
            return emails_count >= MIN_EMAILS_CIBLE
        return len(valid_leads) >= effective_limit

    def _enrichir_place(place: dict):
        nom     = place.get("nom", "Inconnu")
        website = place.get("site_web")
        email   = None
        statut_email = None
        _email_result = None

        if website:
            domain = extract_domain(website)
            blacklist = ["google.com", "facebook.com", "instagram.com",
                         "tripadvisor", "yellowpages", "yandex.com", "yahoo.com"]
            if domain and any(bd in domain.lower() for bd in blacklist):
                place["site_web"] = None
                website = None
                domain  = None

            if domain:
                _email_result = None
                if _EMAIL_FINDER_AVAILABLE:
                    _email_result = find_email_all_methods(website, verbose=True)  # noqa
                    if _email_result['email']:
                        email  = _email_result['email']
                        source = _email_result.get('source', 'site')
                        confidence = _email_confidence(_email_result)
                        print(f"   [{nom}] Email trouvé ({source}, confiance {confidence}%) : {email}")
                elif website:
                    email = search_email_on_website(website)
                    if email:
                        print(f"   [{nom}] Email page web (legacy) : {email}")

        email_source_info = None
        if email:
            statut_email = verify_email_mailcheck(email)
            if statut_email != "valid":
                print(f"   [{nom}] Email {email} -> statut: {statut_email}")
            if _email_result and _email_result.get('email'):
                email_source_info = f"{_email_result.get('source','?')}|conf:{_email_confidence(_email_result)}"

        telephone = place.get('telephone', '')
        if not telephone and website:
            tel_web = search_phone_on_website(website)
            if tel_web:
                telephone = tel_web
                print(f"   [{nom}] Téléphone trouvé sur site : {telephone}")

        if not email and not telephone:
            print(f"   [{nom}] [REJETE] Aucun email ni téléphone trouvé.")
            return None

        return {
            'nom':          nom,
            'adresse':      place.get('adresse', ''),
            'site_web':     website or '',
            'telephone':    telephone,
            'rating':       place.get('rating', ''),
            'nb_avis':      int(place.get('nb_avis') or 0),
            'email':        email or '',
            'statut_email': statut_email or '',
            'email_source': email_source_info or '',
            'date_scraping': date_scraping,
            'mot_cle':      args.keyword,
            'ville':        args.city,
            'category':     place.get('category', ''),
            'lien_maps':    place.get('lien_maps', ''),
            'campaign_id':  args.campaign_id,
        }

    # ================================================================
    # BOUCLE PRINCIPALE — ne s'arrête que si l'objectif est atteint
    # ou si toutes les zones sont épuisées
    # ================================================================
    passe_num = 0

    while zones_queue and not _objectif_atteint():
        zone = zones_queue.pop(0)
        if zone.lower() in zones_used:
            continue
        zones_used.add(zone.lower())
        passe_num += 1

        # Taille de la requête pour cette zone
        if MIN_EMAILS_CIBLE:
            manquants  = MIN_EMAILS_CIBLE - emails_count
            limit_zone = min(MAX_PAR_PASSE, max(manquants * 5, 20))
        else:
            limit_zone = min(MAX_PAR_PASSE, effective_limit - len(valid_leads))

        print(f"\n{'='*60}")
        print(f"Passe {passe_num}/{len(zones_used) + len(zones_queue)} : {args.keyword} @ {zone}")
        if MIN_EMAILS_CIBLE:
            print(f"   Emails trouvés : {emails_count}/{MIN_EMAILS_CIBLE}")
        else:
            print(f"   Leads collectés : {len(valid_leads)}/{effective_limit}")
        print(f"{'='*60}")

        try:
            batch_places = 
                scrape_google_maps(args.keyword, zone, limit_zone, known_names=seen_noms_global
            )
        except Exception as e:
            print(f"   [ERREUR] Scraping zone '{zone}' : {e}")
            time.sleep(3)
            continue

        if not batch_places:
            print(f"   [WARN] Aucun résultat pour '{zone}'.")
            continue

        # Déduplication
        nouveaux = [p for p in batch_places
                    if p.get('nom', '').strip().lower() not in seen_noms_global
                    and not seen_noms_global.add(p.get('nom', '').strip().lower())]

        print(f"   -> {len(nouveaux)} nouveaux lieux (sur {len(batch_places)} trouvés)")

        for place in nouveaux:
            if _objectif_atteint():
                print(f"\n   [OK] Objectif atteint → arrêt immédiat.")
                break

            lead = _enrichir_place(place)
            if lead is None:
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
                print(f"   [PROGRESSION] emails={emails_count}/{MIN_EMAILS_CIBLE}  leads={len(valid_leads)} (total: {len(valid_leads)})")
            else:
                print(f"   [PROGRESSION] leads={len(valid_leads)}/{effective_limit} (total: {len(valid_leads)})")

        # Si la file est épuisée mais l'objectif n'est pas atteint,
        # ajouter automatiquement des zones de repli (évite l'arrêt prématuré
        # quand la zone principale contenait surtout des leads déjà connus)
        if not zones_queue and not _objectif_atteint() and not args.multi_zone:
            _fallbacks = [
                f"{args.city} centre",
                f"{args.city} nord", f"{args.city} sud",
                f"{args.city} est",  f"{args.city} ouest",
                f"{args.city} 1er arrondissement", f"{args.city} 2ème arrondissement",
                f"{args.city} 3ème arrondissement", f"{args.city} 4ème arrondissement",
                f"{args.city} 5ème arrondissement", f"{args.city} 6ème arrondissement",
                f"{args.city} 7ème arrondissement", f"{args.city} 8ème arrondissement",
                f"{args.city} 9ème arrondissement", f"{args.city} 10ème arrondissement",
                f"{args.city} 11ème arrondissement", f"{args.city} 12ème arrondissement",
                f"{args.city} 13ème arrondissement", f"{args.city} 14ème arrondissement",
                f"{args.city} 15ème arrondissement", f"{args.city} 16ème arrondissement",
                f"{args.city} 17ème arrondissement", f"{args.city} 18ème arrondissement",
                f"{args.city} 19ème arrondissement", f"{args.city} 20ème arrondissement",
            ]
            _new_zones = [z for z in _fallbacks if z.lower() not in zones_used]
            if _new_zones:
                if MIN_EMAILS_CIBLE:
                    manque = MIN_EMAILS_CIBLE - emails_count
                    print(f"\n   [AUTO-ZONE] Objectif emails non atteint ({emails_count}/{MIN_EMAILS_CIBLE}, "
                          f"encore {manque} email(s) à trouver). "
                          f"Ajout de {len(_new_zones)} zones de repli...")
                else:
                    manque = effective_limit - len(valid_leads)
                    print(f"\n   [AUTO-ZONE] Objectif non atteint ({len(valid_leads)}/{effective_limit}, "
                          f"encore {manque} lead(s) à trouver). "
                          f"Ajout de {len(_new_zones)} zones de repli...")
                zones_queue.extend(_new_zones)

        time.sleep(2)

    # ================================================================
    # RÉSUMÉ FINAL
    # ================================================================
    elapsed = time.time() - start_time
    try:
        mem_mb = psutil.Process().memory_info().rss / 1024 / 1024
    except:
        mem_mb = 0

    print("")
    print("=" * 60)
    nb_avec_site  = sum(1 for l in valid_leads if l['site_web'])
    nb_sans_site  = sum(1 for l in valid_leads if not l['site_web'])
    nb_avec_email = sum(1 for l in valid_leads if l['email'])

    if MIN_EMAILS_CIBLE and nb_avec_email < MIN_EMAILS_CIBLE:
        print(f"[PARTIEL] Objectif {MIN_EMAILS_CIBLE} emails NON ATTEINT.")
        print(f"   Emails trouvés  : {nb_avec_email} / {MIN_EMAILS_CIBLE}")
        print(f"   Zones explorées : {len(zones_used)}")
        print(f"   [CONSEIL] Activez 'Multi-zones' pour explorer les quartiers.")
    elif MIN_EMAILS_CIBLE:
        print(f"[SUCCES] Objectif {MIN_EMAILS_CIBLE} emails ATTEINT ✓")
    else:
        print(f"Scraping terminé — {len(valid_leads)} leads extraits")

    print(f"   Total leads      : {len(valid_leads)}")
    print(f"   Avec site web    : {nb_avec_site}")
    print(f"   Sans site web    : {nb_sans_site}")
    print(f"   Avec email       : {nb_avec_email}")
    print(f"   Passes effectuées: {passe_num}")
    print(f"   Durée            : {elapsed:.1f}s")
    print(f"   RAM utilisée     : {mem_mb:.1f} Mo")
    print("=" * 60)


if __name__ == "__main__":
    main()


