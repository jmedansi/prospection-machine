# -*- coding: utf-8 -*-
"""
services/email_generator.py
Gère la détermination du profil et la génération du contenu email.
"""
import os
import re
from typing import Dict, Any
from database import get_conn, logger
from copywriter.main import (
    get_all_impacts, extract_problemes_detectes, 
    determine_main_problem, generate_email_content
)
from envoi.email_builder import build_premium_email


def auto_categorize_lead(lead_id: int) -> str:
    """
    Auto-catégorise un lead si category est vide.
    Priorité: category (GMB) > mot_cle > nom (heuristique).
    Met à jour leads_bruts.category en DB.
    Retourne la catégorie détectée.
    """
    with get_conn() as conn:
        row = conn.execute(
            "SELECT category, mot_cle, nom FROM leads_bruts WHERE id=?", (lead_id,)
        ).fetchone()
        if not row:
            return ''
        
        category = (row['category'] or '').strip()
        if category:
            return category
        
        mot_cle = (row['mot_cle'] or '').strip().lower()
        nom = (row['nom'] or '').strip()
        
        # Détection par mot-clé (prioritaire)
        category = _detect_category_from_text(mot_cle)
        if not category:
            # Détection par nom d'entreprise
            category = _detect_category_from_text(nom)
        
        if category:
            conn.execute(
                "UPDATE leads_bruts SET category=? WHERE id=?",
                (category, lead_id)
            )
            conn.commit()
            logger.info(f"[AutoCat] Lead {lead_id}: category → '{category}'")
        
        return category


def _detect_category_from_text(text: str) -> str:
    """Détecte la catégorie à partir d'un texte (mot-clé ou nom)."""
    if not text:
        return ''
    t = text.lower()
    
    # Mapping keywords → catégorie GMB standardisée
    KEYWORD_TO_CATEGORY = {
        # Restauration
        'restaurant': 'Restaurant',
        'café': 'Café', 'cafe': 'Café',
        'boulangerie': 'Boulangerie',
        'pâtisserie': 'Pâtisserie',
        'pizzeria': 'Pizzeria',
        'brasserie': 'Brasserie',
        'bistro': 'Bistro',
        'créperie': 'Créperie',
        'traiteur': 'Traiteur',
        'bar': 'Bar',
        'snack': 'Snack',
        'kebab': 'Kebab',
        'sushi': 'Restaurant japonais',
        'ramen': 'Restaurant japonais',
        'hamburger': 'Restaurant de hamburgers',
        'fast food': 'Restauration rapide',
        # Hôtellerie
        'hôtel': 'Hôtel', 'hotel': 'Hôtel',
        'auberge': 'Auberge',
        'camping': 'Camping',
        'gîte': 'Gîte',
        'chambre d\'hôte': 'Chambre d\'hôtes',
        # Santé
        'dentiste': 'Cabinet dentaire',
        'cabinet dentaire': 'Cabinet dentaire',
        'médecin': 'Cabinet médical',
        'clinique': 'Clinique',
        'pharmacie': 'Pharmacie',
        'kiné': 'Cabinet de kinésithérapie',
        'ostéopathe': 'Cabinet d\'ostéopathie',
        'psychologue': 'Cabinet de psychologue',
        'opticien': 'Opticien',
        'vétérinaire': 'Vétérinaire',
        # Beauté
        'coiffeur': 'Salon de coiffure',
        'coiffure': 'Salon de coiffure',
        'barbier': 'Barbier',
        'salon': 'Salon',
        'esthétique': 'Institut de beauté',
        'spa': 'Spa',
        'tatoueur': 'Salon de tatouage',
        # Artisanat
        'plombier': 'Plombier',
        'électricien': 'Électricien',
        'maçon': 'Maçon',
        'peintre': 'Peintre',
        'couvreur': 'Couvreur',
        'carreleur': 'Carreleur',
        'menuisier': 'Menuisier',
        'serrurier': 'Serrurier',
        'chauffagiste': 'Chauffagiste',
        'clim': 'Installateur climatisation',
        'climatisation': 'Installateur climatisation',
        'jardinier': 'Jardinier',
        'paysagiste': 'Paysagiste',
        'nettoyage': 'Entreprise de nettoyage',
        'déménagement': 'Déménageur',
        # Auto
        'garage': 'Garage',
        'automobile': 'Garage',
        'pneu': 'Pneumaticien',
        'carrosserie': 'Carrossier',
        'lavage': 'Lavage automobile',
        # Commerce
        'magasin': 'Magasin',
        'boutique': 'Boutique',
        'commerce': 'Commerce',
        'librairie': 'Librairie',
        'fleuriste': 'Fleuriste',
        'jouet': 'Magasin de jouets',
        # Services
        'agence': 'Agence',
        'web': 'Agence web',
        'marketing': 'Agence marketing',
        'communication': 'Agence de communication',
        'comptable': 'Expert-comptable',
        'comptabilité': 'Expert-comptable',
        'expert comptable': 'Expert-comptable',
        'avocat': 'Cabinet d\'avocat',
        'notaire': 'Étude notariale',
        'assurance': 'Courtier en assurance',
        'immobilier': 'Agence immobilière',
        'formation': 'Organisme de formation',
        'informatique': 'Prestataire informatique',
        'développeur': 'Développeur web',
        'photographe': 'Photographe',
        'vidéo': 'Vidéaste',
        # Sport
        'sport': 'Salle de sport',
        'gym': 'Salle de sport',
        'fitness': 'Salle de fitness',
        'coach': 'Coach sportif',
        'piano': 'Professeur de musique',
        'guitare': 'Professeur de musique',
        'musique': 'Professeur de musique',
    }
    
    # Matching par mot-clé (le plus long en premier)
    matches = []
    for keyword, cat in KEYWORD_TO_CATEGORY.items():
        if keyword in t:
            matches.append((len(keyword), cat))
    
    if matches:
        matches.sort(reverse=True)  # Le plus long mot-clé en premier
        return matches[0][1]
    
    return ''

# Mapping situation (phrase_synthese) -> Profil (Source: AGENTS.md)
SITUATION_TO_PROFILE = {
    'Site lent sur mobile':        'B',
    'Bon GMB, mauvais site':       'B',
    'Pas de bouton contact / tel': 'B',
    'CMS vieillot (Wix/Jimdo)':   'B',
    'Pas de meta description':     'D',
    "Peu d'avis Google":           'C',
    'Note Google faible':          'C',
    'Pas de site web':             'A',
}

def determine_profile_v9(audit_dict: Dict[str, Any]) -> str:
    """
    Détermine le profil email (A, B, C, D) en fonction des données d'audit.
    Logique centralisée basée sur copywriter.main.
    """
    try:
        impacts = get_all_impacts(audit_dict)
        problemes = extract_problemes_detectes(impacts, audit_dict)
        main_prob = determine_main_problem(problemes, impacts)
        
        if not main_prob:
            return 'B' # Fallback
            
        copy_res = generate_email_content(audit_dict, main_prob)
        situation = copy_res.get('phrase_synthese', '')
        
        return SITUATION_TO_PROFILE.get(situation, 'B')
    except Exception as e:
        logger.error(f"Erreur determine_profile_v9: {e}")
        return 'B'

_SNIPER_SOURCES = {"ads", "tech", "jobs", "bodacc"}


def generate_email_for_lead(lead_id: int) -> bool:
    """
    Génère l'objet et le corps HTML pour un lead audité.
    Redirige vers sniper/email_generator pour les leads Sniper.
    """
    try:
        # Auto-catégoriser si category vide
        auto_categorize_lead(lead_id)
        
        # ── Routing Sniper ────────────────────────────────────────────────────
        with get_conn() as conn:
            src_row = conn.execute(
                "SELECT source FROM leads_bruts WHERE id=?", (lead_id,)
            ).fetchone()
        if src_row and src_row["source"] in _SNIPER_SOURCES:
            from sniper.email_generator import generate_sniper_email_for_lead
            return generate_sniper_email_for_lead(lead_id)

        with get_conn() as conn:
            row = conn.execute("""
                SELECT lb.id, lb.nom, lb.ville, lb.category, lb.site_web, lb.email, lb.telephone,
                       lb.rating, lb.nb_avis, lb.prenom_gerant,
                       la.mobile_score, la.score_seo, la.score_urgence, la.lcp_ms,
                       la.has_meta_description, la.has_contact_button, la.tel_link, la.cms_detected,
                       la.lien_rapport, la.ceo_prenom, la.template_used
                FROM leads_bruts lb
                JOIN leads_audites la ON la.lead_id = lb.id
                WHERE lb.id = ?
            """, (lead_id,)).fetchone()
            
            if not row:
                return False

            audit_dict = {
                'lead_id': row[0],
                'nom': row[1],
                'ville': row[2],
                'category': row[3],
                'site_web': row[4],
                'email': row[5],
                'telephone': row[6],
                'rating': row[7] or 0,
                'nb_avis': row[8] or 0,
                'prenom_gerant': row[9] or '',
                'mobile_score': row[10] or 0,
                'score_seo': row[11] or 0,
                'score_urgence': row[12] or 0,
                'lcp_ms': row[13] or 0,
                'has_meta_description': bool(row[14]) if row[14] is not None else True,
                'has_contact_button': bool(row[15]) if row[15] is not None else True,
                'tel_link': bool(row[16]) if row[16] is not None else True,
                'cms_detected': row[17] or '',
                'lien_rapport': row[18] or '',
                'ceo_prenom': row[19] or '',
                'template_used': row[20] or '',
            }
            
            profile = determine_profile_v9(audit_dict)
            audit_dict['profile'] = profile
            audit_dict['prospect_nom'] = audit_dict['nom']
            
            if not audit_dict.get('lien_rapport'):
                clean_nom = re.sub(r'[^a-zA-Z0-9]', '-', audit_dict['nom'].lower())
                audit_dict['lien_rapport'] = f"https://audit.incidenx.com/{clean_nom}"
            
            # Utiliser Mail 1 (secteur-specifique) depuis sequence_emails
            # SAUF pour les leads maps sans site (maquette) — utiliser build_premium_email
            secteur = ''
            with get_conn() as conn:
                br = conn.execute("SELECT secteur, category, source FROM leads_bruts WHERE id=?", (lead_id,)).fetchone()
                if br:
                    secteur = (br['secteur'] or br['category'] or '')
                    source = br['source'] or ''

            is_maps_no_site = (source == 'maps' and audit_dict.get('template_used') == 'maquette')

            if is_maps_no_site:
                # Profil A : email template directement via build_premium_email
                html_content = build_premium_email(audit_dict, verify_link=False)
                email_objet = f"Profil {profile} - Analyse pour {audit_dict['nom']}"
                title_match = re.search(r'<title>([^<]+)</title>', html_content)
                if title_match:
                    email_objet = title_match.group(1).strip()
            else:
                try:
                    from envoi.sequence_emails import get_mail_1

                    mail1 = get_mail_1(secteur)
                    if mail1:
                        email_objet = mail1.get('subject', f"Profil {profile} - Analyse pour {audit_dict['nom']}")
                        body_text = mail1.get('body', '')
                        # Remplacer [Prénom] par le prenom du gerant
                        prenom = audit_dict.get('prenom_gerant', '') or ''
                        body_text = body_text.replace('[Prénom]', prenom if prenom else '')
                        # Wrapper HTML simple (aucune modification du contenu)
                        html_content = '<html><head><title>{}</title></head><body><pre style="font-family:inherit;white-space:pre-wrap">{}</pre></body></html>'.format(
                            email_objet, body_text
                        )
                    else:
                        raise Exception("Mail 1 not found")
                except Exception as e:
                    logger.warning(f"[Email] Mail 1 fallback for lead {lead_id}: {e}")
                    # Immobilier : ne JAMAIS fallback sur build_premium_email
                    if 'immo' in secteur.lower():
                        logger.error(f"[Email] Lead immobilier {lead_id} — pas de mail secteur trouvé, skip")
                        return False
                    # fallback vers le builder complet (autres secteurs uniquement)
                    html_content = build_premium_email(audit_dict, verify_link=False)
                    email_objet = f"Profil {profile} - Analyse pour {audit_dict['nom']}"
                    title_match = re.search(r'<title>([^<]+)</title>', html_content)
                    if title_match:
                        email_objet = title_match.group(1).strip()
            
            conn.execute("""
                UPDATE leads_audites 
                SET email_objet = ?, email_corps = ?, profile = ?
                WHERE lead_id = ?
            """, (email_objet, html_content, profile, lead_id))
            conn.commit()
            return True
            
    except Exception as e:
        logger.error(f"Erreur generate_email_for_lead({lead_id}): {e}")
        return False
