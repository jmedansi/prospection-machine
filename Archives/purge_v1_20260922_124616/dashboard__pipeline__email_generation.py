# -*- coding: utf-8 -*-
"""
dashboard/pipeline/email_generation.py
Logique de génération d'email pour le pipeline.
"""
import os
import re
import random
import logging
from database.db_manager import get_conn
from envoi.email_tracking_service import EmailTrackingService
from envoi.email_builder import build_premium_email
from copywriter.main import (
    get_all_impacts, extract_problemes_detectes,
    determine_main_problem, generate_email_content,
)

logger = logging.getLogger(__name__)

# Mapping situation -> Profil (Source: AGENTS.md)
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

def generate_email_for_lead(lead_id: int) -> bool:
    """
    Génère email_objet + email_corps pour un lead via les fonctions pures
    du copywriter, puis sauvegarde dans leads_audites et emails_envoyes.
    """
    try:
        with get_conn() as conn:
            row = conn.execute("""
                SELECT
                    lb.id, lb.nom, lb.email, lb.ville,
                    lb.category, lb.site_web, lb.telephone,
                    lb.rating, lb.nb_avis        AS reviews_count,
                    la.mobile_score, la.desktop_score,
                    la.lcp_ms, la.fcp_ms, la.cls,
                    la.has_https, la.has_meta_description,
                    la.h1_count, la.render_blocking_scripts,
                    la.uses_cache, la.tel_link, la.has_contact_button,
                    la.images_without_alt, la.has_analytics,
                    la.cms_detected, la.score_performance,
                    la.score_seo, la.score_gmb, la.lien_rapport,
                    la.statut AS site_analysee
                FROM leads_bruts lb
                JOIN leads_audites la ON la.lead_id = lb.id
                WHERE lb.id = ?
            """, (lead_id,)).fetchone()

        if not row:
            return False

        audit_dict = dict(row)

        impacts   = get_all_impacts(audit_dict)
        problemes = extract_problemes_detectes(impacts, audit_dict)
        main_prob = determine_main_problem(problemes, impacts)

        if not main_prob:
            return False

        copy_res  = generate_email_content(audit_dict, main_prob)
        situation = copy_res.get('phrase_synthese', '')
        profile = SITUATION_TO_PROFILE.get(situation, 'B')
        
        # A/B Testing : Allocation aléatoire 50/50 
        variant = random.choice(['v1', 'v2'])
        audit_dict['template_variant'] = variant

        # Résoudre l'URL du rapport
        lien = audit_dict.get('lien_rapport') or ''
        if lien.startswith('local://'):
            slug = lien.replace('local://', '').strip('/')
            lien = f'https://audit.incidenx.com/{slug}/'

        # CEO Finder
        if not audit_dict.get('prenom_gerant'):
            site_web = audit_dict.get('site_web')
            if site_web:
                try:
                    from core.contact_finder import find_contacts
                    contacts = find_contacts(site_web, audit_dict.get('nom', ''), pays=audit_dict.get('pays', 'fr'), enrich_ceo=True)
                    prenom = contacts.get('ceo_prenom')
                    nom_ceo = contacts.get('ceo_nom')
                    if prenom:
                        audit_dict['prenom_gerant'] = prenom
                        audit_dict['nom_gerant'] = nom_ceo
                        with get_conn() as conn:
                            conn.execute("UPDATE leads_bruts SET prenom_gerant=?, nom_gerant=? WHERE id=?",
                                         (prenom, nom_ceo, lead_id))
                            conn.commit()
                except Exception as e:
                    logger.warning(f"contact_finder CEO échoué pour lead {lead_id}: {e}")

        # Générer le HTML
        builder_data = {**audit_dict, 'profile': profile, 'lien_rapport': lien or 'https://incidenx.com'}
        email_corps = build_premium_email(builder_data, verify_link=False)

        if not email_corps:
            return False

        # Extraire le sujet
        title_match = re.search(r'<title>([^<]+)</title>', email_corps)
        email_objet = title_match.group(1) if title_match else situation

        # Mise à jour leads_audites
        with get_conn() as conn:
            conn.execute("""
                UPDATE leads_audites
                SET email_objet=?, email_corps=?, approuve=0, template_variant=?
                WHERE lead_id=?
            """, (email_objet, email_corps, variant, lead_id))
            conn.commit()

        # Ajout dans emails_envoyes via EmailTrackingService
        tracking_service = EmailTrackingService(db_path=os.getenv('DB_PATH', 'data/prospection.db'))
        tracking_service.create_email_record(
            lead_id=lead_id,
            email=audit_dict.get('email'),
            subject=email_objet,
            body=email_corps,
            lien_rapport=lien,
            approuve=0
        )

        return True

    except Exception as e:
        logger.error(f"[PIPELINE-Email] generate_email_for_lead #{lead_id}: {e}")
        return False
