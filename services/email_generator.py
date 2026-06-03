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
                       lb.rating, lb.nb_avis,
                       la.mobile_score, la.score_seo, la.score_urgence, la.lcp_ms,
                       la.has_meta_description, la.has_contact_button, la.tel_link, la.cms_detected,
                       la.lien_rapport
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
                'mobile_score': row[9] or 0,
                'score_seo': row[10] or 0,
                'score_urgence': row[11] or 0,
                'lcp_ms': row[12] or 0,
                'has_meta_description': bool(row[13]) if row[13] is not None else True,
                'has_contact_button': bool(row[14]) if row[14] is not None else True,
                'tel_link': bool(row[15]) if row[15] is not None else True,
                'cms_detected': row[16] or '',
                'lien_rapport': row[17] or '',
            }
            
            profile = determine_profile_v9(audit_dict)
            audit_dict['profile'] = profile
            audit_dict['prospect_nom'] = audit_dict['nom']
            
            if not audit_dict.get('lien_rapport'):
                clean_nom = re.sub(r'[^a-zA-Z0-9]', '-', audit_dict['nom'].lower())
                audit_dict['lien_rapport'] = f"https://audit.incidenx.com/{clean_nom}"
            
            html_content = build_premium_email(audit_dict, verify_link=False)
            
            # Extraction de l'objet depuis <title> du HTML (Règle AGENTS.md)
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
