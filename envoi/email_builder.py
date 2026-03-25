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
        return None
    
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
    template_filename = f"template_profil_{profile.lower()}.html"
    template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates', 'emails')
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

    if profile == "B":
        html = html.replace('{{LCP}}', str(lcp_s))
        html = html.replace('{{IMPACT}}', f"votre score mobile est de {int(mobile_score)}/100 — vos concurrents sont à 75/100 en moyenne.")
        html = html.replace('{{PERTE}}', "plus de la moitié de vos visiteurs repartent sans avoir vu vos services ni votre numéro de téléphone.")
        html = html.replace('{{LIEN}}', "Par ailleurs, même un site rapide ne suffit pas si Google ne peut pas l'afficher correctement dans ses résultats. J'ai aussi analysé votre référencement.")
        html = html.replace('{{OUTRO}}', f"J'ai préparé une analyse complète pour {nom} avec les 3 actions prioritaires pour passer sous les 3 secondes.")
    
    elif profile == "C":
        html = html.replace('{{RATING}}', str(rating))
        html = html.replace('{{REVIEWS}}', str(reviews))
        html = html.replace('{{IMPACT}}', f"la moyenne dans votre secteur à {ville} est 4.5/5 avec plus de 50 avis.")
        html = html.replace('{{PERTE}}', "9 prospects sur 10 choisissent un concurrent mieux noté avant même de visiter votre site.")
        html = html.replace('{{OUTRO}}', f"J'ai préparé une analyse de votre fiche Google et une stratégie pour doubler vos avis en 30 jours.")
    
    elif profile == "A":
        html = html.replace('{{IMPACT}}', f"vos concurrents {category.lower()} à {ville} captent ces recherches chaque jour à votre place.")
        html = html.replace('{{PERTE}}', "chaque semaine, des clients potentiels vous cherchent en ligne et contactent directement un concurrent.")
        html = html.replace('{{OUTRO}}', f"J'ai préparé une maquette de ce que pourrait être votre site — personnalisée pour {nom}.")
    
    elif profile == "D":
        html = html.replace('{{IMPACT}}', "votre site manque d'éléments essentiels pour être référencé sur Google.")
        html = html.replace('{{PERTE}}', "vos clients potentiels ne vous trouvent pas sur les mots-clés qui comptent pour votre activité.")
        html = html.replace('{{LIEN}}', "Par ailleurs, j'ai aussi analysé la performance de votre site. Un référencement optimal ne suffit pas si votre site met plus de 3 secondes à charger.")
        html = html.replace('{{OUTRO}}', f"J'ai préparé une analyse SEO de {nom} avec les actions prioritaires pour améliorer votre visibilité.")

    return html
