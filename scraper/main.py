import sys
import os
import argparse
import logging
import requests
import re
from urllib.parse import urlparse
from datetime import datetime

# Ajout du répertoire parent au sys.path pour importer config_manager
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config_manager import get_config, increment_usage, check_limits, get_sheet
from gemini_maps import get_places_json

# Configuration du logging
logging.basicConfig(
    filename='errors.log',
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def extract_domain(url):
    """Extrait le domaine d'une URL."""
    if not url:
        return None
    try:
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain
    except Exception as e:
        logging.error(f"Erreur d'extraction de domaine depuis {url}: {e}")
        return None

def search_email_hunter(domain, api_key):
    """Cherche un email pour le domaine via Hunter.io."""
    url = "https://api.hunter.io/v2/domain-search"
    params = {
        "domain": domain,
        "api_key": api_key
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        emails = data.get('data', {}).get('emails', [])
        if emails:
            return emails[0].get('value')
        return None
    except Exception as e:
        logging.error(f"Erreur Hunter.io pour {domain}: {e}")
        return None

def search_email_on_website(url):
    """Cherche un email directement sur la page web (fallback pour Hunter)."""
    if not url:
        return None
    try:
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
            
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        
        # Regex pour une adresse email
        emails_trouves = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', response.text)
        
        # Filtrer les faux positifs (comme email@sentry.io, etc.)
        faux_positifs = ['.png', '.jpg', '.jpeg', '.gif', 'sentry', 'wix', 'example', 'domain.com']
        
        for email in emails_trouves:
            email = email.lower()
            if not any(fp in email for fp in faux_positifs):
                return email # Retourner le premier email valide
                
        return None
    except Exception as e:
        logging.error(f"Erreur de recherche sur le site {url} : {e}")
        return None

def verify_email_mailcheck(email):
    """Vérifie l'email via Mailcheck.ai."""
    url = f"https://api.mailcheck.ai/email/{email}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return data.get('status')
    except Exception as e:
        logging.error(f"Erreur Mailcheck.ai pour {email}: {e}")
        return None

def write_leads_to_sheets(leads):
    """Écrit une liste de leads dans la feuille Google Sheets 'leads_bruts'."""
    if not leads:
        return
    try:
        sheet = get_sheet("leads_bruts")
        
        # Format des lignes: Date de scraping | Mot-clé | Nom du restaurant | Adresse | Téléphone | Site web | Note | Avis | Email de contact | Statut Email | Service proposé | Mail à envoyer
        rows_to_insert = []
        for lead in leads:
            rows_to_insert.append([
                lead.get('date_scraping', ''),
                lead.get('keyword', ''),
                lead.get('nom', ''),
                lead.get('adresse', ''),
                lead.get('telephone', ''),
                lead.get('site_web', ''),
                lead.get('rating', ''),
                lead.get('nb_avis', ''),
                lead.get('email', ''),
                lead.get('statut_email', ''),
                lead.get('service', ''),
                lead.get('mail_brouillon', '')
            ])
            
        sheet.append_rows(rows_to_insert)
    except Exception as e:
        logging.error(f"Erreur lors de l'écriture dans Google Sheets: {e}")

def main():
    parser = argparse.ArgumentParser(description="Agent Scraper pour Google Places et Hunter.io")
    parser.add_argument("--keyword", required=True, help="Le métier (ex: 'restaurant')")
    parser.add_argument("--city", required=True, help="La ville (ex: 'Cotonou')")
    args = parser.parse_args()

    print(f"Lancement du scraping pour '{args.keyword}' à '{args.city}'...")

    config = get_config()
    if not config:
        print("Erreur: Aucune configuration active trouvée dans Google Sheets.")
        sys.exit(1)

    google_api_key = config.get("google_api_key")
    hunter_api_key = config.get("hunter_key")

    if not google_api_key or not hunter_api_key:
        print("Erreur: Clés API Google ou Hunter manquantes dans la configuration.")
        logging.error("Clés API manquantes.")
        sys.exit(1)

    # Nous utilisons dorénavant Gemini Maps au lieu de Google Places
    places = get_places_json(args.keyword, args.city)
    if not places:
        print("Aucun établissement trouvé.")
        sys.exit(0)

    print(f"{len(places)} établissements trouvés. Début de l'analyse...")

    valid_leads = []
    unwritten_leads = []
    date_scraping = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for place in places:
        # 1. Détails Gemini Maps
        website = place.get("site_web")
        
        domain = None
        if not website:
            print(f"[{place.get('nom')}] Pas de site web renseigné")
        else:
            domain = extract_domain(website)
            if not domain:
                print(f"[{place.get('nom')}] Domaine non extrait de {website}")
                
            blacklisted_domains = ["google.com", "facebook.com", "instagram.com", "yandex.com", "yahoo.com", "tripadvisor", "yellowpages"]
            if domain and any(bd in domain.lower() for bd in blacklisted_domains):
                print(f"[{place.get('nom')}] Domaine ignoré volontairement: {domain}")
                domain = None
                website = None

        email = place.get('email')
        if email:
            print(f"[{place.get('nom')}] Email trouvé par Gemini Maps : {email}")
            
        status = None

        if not email and website and domain:
            # Vérification des limites Hunter uniquement si on a un domaine
            limits = check_limits()
            hunter_limit_reached = any("Hunter" in w for w in limits)
            if hunter_limit_reached:
                logging.warning("Arrêt: Limite Hunter atteinte ('hunter_almost_full' ou similaire).")
                print("Limite Hunter atteinte. L'email ne sera pas cherché pour ce lead.")
            else:
                # 2. Recherche Hunter.io
                email = search_email_hunter(domain, hunter_api_key)
                increment_usage('hunter')

                if email:
                    print(f"[{place.get('nom')}] Email trouvé par Hunter : {email}")
                else:
                    print(f"[{place.get('nom')}] Aucun email via Hunter, recherche sur le site {website}...")
                    email = search_email_on_website(website)
                    if email:
                        print(f"[{place.get('nom')}] Email trouvé sur la page web : {email}")
                    else:
                        print(f"[{place.get('nom')}] Aucun email trouvé sur le site web.")

        if email:
            # 3. Vérification Mailcheck.ai
            status = verify_email_mailcheck(email)
            if status != "valid":
                print(f"[{place.get('nom')}] Email {email} jugé invalide ou incertain par Mailcheck, statut: {status}")

        # 4. Classification du Prospect
        nom = place.get('nom', '')
        if website:
            service = "Optimisation site web"
            mail = f"Bonjour {nom},\n\nJ'ai remarqué que votre site {website} pourrait être optimisé pour améliorer les réservations en ligne et offrir une expérience plus moderne à vos clients.\n\nJe propose d'Optimiser votre site pour faciliter les réservations et mettre en valeur votre menu.\n\nBien cordialement,\nAntigravity"
        else:
            service = "Créer site web"
            mail = f"Bonjour {nom},\n\nJ'ai remarqué que vous n'avez pas de site web, un outil qui pourrait améliorer les réservations en ligne et offrir une expérience plus moderne à vos clients.\n\nJe propose de Créer un site web pour faciliter les réservations et mettre en valeur votre menu.\n\nBien cordialement,\nAntigravity"

        # Lead validé
        lead = {
            'nom': nom,
            'adresse': place.get('adresse', ''),
            'site_web': website,
            'telephone': place.get('telephone', ''),
            'gmb_id': place.get('gmb_id', ''), # Facultatif avec Gemini Maps
            'rating': place.get('rating', ''),
            'nb_avis': place.get('nb_avis', ''),
            'email': email,
            'statut_email': status,
            'date_scraping': date_scraping,
            'keyword': args.keyword,
            'service': service,
            'mail_brouillon': mail
        }

        # Affichage
        print(f"✓ {lead['nom']} — {lead['email']} — rating {lead['rating']}/5")
        
        valid_leads.append(lead)
        unwritten_leads.append(lead)

        # 4. Écriture si 5 leads non écrits
        if len(unwritten_leads) >= 5:
            write_leads_to_sheets(unwritten_leads)
            unwritten_leads = []

    # Écriture des leads restants à la fin
    if unwritten_leads:
        write_leads_to_sheets(unwritten_leads)

    print(f"Terminé. {len(valid_leads)} leads validés et écrits dans Google Sheets.")

if __name__ == "__main__":
    main()
