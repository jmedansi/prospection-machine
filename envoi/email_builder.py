# -*- coding: utf-8 -*-
"""
Module envoi/email_builder.py
Genere les emails de prospection via templates fixes.
Template A: sans site web
Template B: site lent / mal optimise
Template C: mauvaise fiche GMB
Template D: SEO incomplet
"""
import os
import re
import requests
import sys

# Chemin racine pour les imports inter-modules (reporter, database, etc.)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.append(ROOT)

def verify_rapport_link(url: str, timeout: int = 5) -> bool:
    """Verifie que le lien du rapport existe (HTTP 200)."""
    try:
        response = requests.head(url, timeout=timeout, allow_redirects=True)
        return response.status_code == 200
    except:
        return False

def build_premium_email(lead_data, verify_link: bool = True):
    """
    Assemble l'email selon le profil.
    
    Args:
        lead_data: dict avec les donnees du prospect
        verify_link: si True, verifie que lien_rapport est accessible
    
    Returns:
        HTML de l'email, ou None si lien non valide (si verify_link=True)
    """
    template_used = lead_data.get('template_used', '')
    template_variant = lead_data.get('template_variant', 'v1')
    explicit_profile = lead_data.get('profile', '').upper()
    
    if template_used in ('ignored', 'failed'):
        return None
    
    if explicit_profile in ('A', 'B', 'C', 'D'):
        profile = explicit_profile
    elif template_used == 'maquette':
        profile = 'A'
    elif template_used == 'audit':
        profile = 'B'
    elif template_used == 'seo':
        profile = 'D'
    elif template_used == 'reputation':
        profile = 'C'
    else:
        import logging
        logging.getLogger(__name__).warning(
            f"email_builder: profil non mappé (template_used='{template_used}', "
            f"explicit_profile='{explicit_profile}') — fallback profil B"
        )
        profile = 'B'
    
    nom = lead_data.get('prospect_nom', '') or lead_data.get('nom', 'votre etablissement')
    nom = re.sub(r'\(Test.*?\)', '', nom).strip()
    if not nom or nom.lower() == "test":
        nom = "votre etablissement"
    
    ville = lead_data.get('ville', '') or ''
    category = lead_data.get('category', '') or lead_data.get('secteur', 'etablissement')
    lcp_ms = lead_data.get('lcp_ms', 0) or 0
    lcp_s = round(float(lcp_ms) / 1000, 1) if lcp_ms else 0
    mobile_score = lead_data.get('mobile_score', 0) or 0
    rating = lead_data.get('rating', 0) or 0
    reviews = lead_data.get('nb_avis', lead_data.get('reviews_count', 0)) or 0
    lien_rapport = lead_data.get('lien_rapport', 'https://incidenx.com')
    
    # Conversion du lien local en lien public GARANTI pour l'email
    # On fait ce remplacement ici pour que le Dashboard (qui lit la DB en local://)
    # ne soit pas perturbé, mais que l'email généré contienne directement le bon lien internet.
    if lien_rapport.startswith("local://"):
        domain = os.getenv("AUDIT_DOMAIN", "audit.incidenx.com")
        slug_local = lien_rapport.replace("local://", "").strip("/")
        lien_rapport = f"https://{domain}/{slug_local}/"
    
    # Verification et republication automatique si necessaire
    if verify_link:
        if not verify_rapport_link(lien_rapport):
            print(f"[ATTENTION] Lien rapport non accessible: {lien_rapport}")
            # Essayer de republicer depuis le HTML stocke
            lead_id = lead_data.get('lead_id')
            if lead_id:
                try:
                    from reporter.main import republish_from_db
                    new_url = republish_from_db(lead_id=lead_id)
                    if new_url:
                        lien_rapport = new_url
                        print(f"[OK] Rapport republication: {lien_rapport}")
                    else:
                        return None
                except Exception as e:
                    print(f"[ERREUR] Republication echouee: {e}")
                    return None
            else:
                return None

    # Template filename
    template_filename = f"template_profil_{profile.lower()}_{template_variant}.html"
    template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates', 'emails')
    template_path = os.path.join(template_dir, template_filename)
    
    if not os.path.exists(template_path):
        # Fallback to v1 if the variant file isn't found
        template_filename = f"template_profil_{profile.lower()}_v1.html"
        template_path = os.path.join(template_dir, template_filename)
        if not os.path.exists(template_path):
            return f"Erreur: Template {template_filename} introuvable dans {template_dir}"

    with open(template_path, 'r', encoding='utf-8') as f:
        html = f.read()

    # Variables communes
    html = html.replace('{{NOM}}', nom)
    html = html.replace('{{VILLE}}', ville)
    html = html.replace('{{CATEGORY}}', category)
    html = html.replace('{{LIEN_RAPPORT}}', lien_rapport)

    prenom = lead_data.get('prenom_gerant')
    nom_etablissement = lead_data.get('nom', 'votre établissement')
    salutation = f"Bonjour {prenom}," if prenom else "Bonjour,"
    html = html.replace('[salutation]', salutation)


    if profile == "B":
        html = html.replace('{{LCP}}', str(lcp_s))

    elif profile == "C":
        html = html.replace('{{RATING}}', str(rating))
        html = html.replace('{{REVIEWS}}', str(reviews))

    screenshot_url = lien_rapport + "preview.png"
    html = html.replace('[screenshot_url]', screenshot_url)

    return html


def build_followup_email(lead_nom):
    """Génère un email de relance simple."""
    subject = f"Re: Audit pour {lead_nom}"
    body = f"""Bonjour,<br><br>
Je me permets de vous relancer car je n'ai pas eu de retour concernant l'audit de performance de votre site.<br>
Avez-vous eu l'occasion d'y jeter un œil ?<br><br>
Bonne journée,<br>Jean-Marc"""
    return subject, body
