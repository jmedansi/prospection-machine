#!/usr/bin/env python
"""
Script pour générer les rapports manquants pour tous les leads audités.
"""
import sys
import os
sys.path.append('.')

from database.connection import get_conn
from reporter.main import generate_and_publish_report
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def safe_run_async(coro):
    """Exécute une coroutine en gérant les conflits de boucle."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            return asyncio.run(coro)
        return loop.run_until_complete(coro)
    except RuntimeError as e:
        if "There is no current event loop" in str(e) or "Event loop is closed" in str(e) or "already running" in str(e):
            try:
                return asyncio.run(coro)
            except RuntimeError as run_e:
                raise e
        raise

def main():
    with get_conn() as conn:
        # Récupérer les leads audités sans rapport
        rows = conn.execute("""
            SELECT la.id, la.lead_id, lb.nom, lb.site_web, lb.category, lb.ville,
                   la.mobile_score, la.desktop_score, la.lcp_ms, la.fcp_ms, la.cls,
                   la.has_https, la.has_meta_description, la.h1_count, la.render_blocking_scripts,
                   la.uses_cache, la.tel_link, la.has_contact_button, la.images_without_alt,
                   la.has_analytics, la.cms_detected, la.score_performance, la.score_seo, la.score_gmb,
                   lb.rating, lb.nb_avis
            FROM leads_audites la
            JOIN leads_bruts lb ON la.lead_id = lb.id
            WHERE (la.lien_rapport IS NULL OR la.lien_rapport = "")
            AND la.statut = 'audite'
            ORDER BY la.id
        """).fetchall()

    print(f"Trouvé {len(rows)} leads sans rapport à générer")

    for i, row in enumerate(rows, 1):
        lead_data = dict(row)
        lead_id = lead_data['lead_id']
        nom = lead_data['nom']

        print(f"[{i}/{len(rows)}] Génération rapport pour {nom} (lead_id: {lead_id})")

        try:
            # Convertir les données pour le format attendu par generate_and_publish_report
            audit_data = {
                'lead_id': lead_id,
                'nom': nom,
                'site_web': lead_data.get('site_web'),
                'category': lead_data.get('category'),
                'ville': lead_data.get('ville'),
                'mobile_score': lead_data.get('mobile_score'),
                'desktop_score': lead_data.get('desktop_score'),
                'lcp_ms': lead_data.get('lcp_ms'),
                'fcp_ms': lead_data.get('fcp_ms'),
                'cls': lead_data.get('cls'),
                'has_https': lead_data.get('has_https'),
                'has_meta_description': lead_data.get('has_meta_description'),
                'h1_count': lead_data.get('h1_count'),
                'render_blocking_scripts': lead_data.get('render_blocking_scripts'),
                'uses_cache': lead_data.get('uses_cache'),
                'tel_link': lead_data.get('tel_link'),
                'has_contact_button': lead_data.get('has_contact_button'),
                'images_without_alt': lead_data.get('images_without_alt'),
                'has_analytics': lead_data.get('has_analytics'),
                'cms_detected': lead_data.get('cms_detected'),
                'score_performance': lead_data.get('score_performance'),
                'score_seo': lead_data.get('score_seo'),
                'score_gmb': lead_data.get('score_gmb'),
                'rating': lead_data.get('rating'),
                'reviews_count': lead_data.get('nb_avis'),
                'has_site': bool(lead_data.get('site_web')),
            }

            # Déterminer le template basé sur les données
            if not audit_data['has_site']:
                audit_data['template_used'] = 'maquette'
            elif audit_data.get('rating', 0) < 4.5 or audit_data.get('reviews_count', 0) < 50:
                audit_data['template_used'] = 'reputation'
            elif audit_data.get('mobile_score', 0) < 60 or audit_data.get('lcp_ms', 0) >= 3000:
                audit_data['template_used'] = 'audit'
            elif not audit_data.get('has_meta_description') or not audit_data.get('has_https'):
                audit_data['template_used'] = 'seo'
            else:
                audit_data['template_used'] = 'audit'  # fallback

            lien_rapport = safe_run_async(generate_and_publish_report(audit_data))

            if lien_rapport:
                with get_conn() as conn:
                    conn.execute(
                        "UPDATE leads_audites SET lien_rapport = ? WHERE lead_id = ?",
                        (lien_rapport, lead_id)
                    )
                    conn.commit()
                print(f"  ✓ Rapport généré: {lien_rapport}")
            else:
                print(f"  ✗ Échec génération rapport pour {nom}")

        except Exception as e:
            logger.error(f"Erreur génération rapport pour {nom} (lead_id: {lead_id}): {e}")
            print(f"  ✗ Erreur: {e}")

if __name__ == '__main__':
    main()