# -*- coding: utf-8 -*-
"""
Script de correction des scores Sniper après bug
- Score desktop et SEO étaient à 0
- Lien rapport apparaissait dans step 1

Usage:
    python sniper_fix_scores.py --preview --limit 30    # Voir les leads
    python sniper_fix_scores.py --dry-run --limit 10    # Simulation
    python sniper_fix_scores.py --limit 50            # Appliquer les corrections
"""

import argparse
import json
import logging
import sys
import os
from typing import Optional, Dict

# Ajouter le root au path
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parse_donnees_audit(raw: Optional[str]) -> dict:
    """Parse le JSON donnees_audit."""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def calculate_score_seo(donnees: dict) -> int:
    """Calcule le score SEO basé sur les données disponibles."""
    if donnees.get('score_seo'):
        return donnees['score_seo']
    
    seo_flags = []
    
    # HTTPS
    if donnees.get('has_https') or donnees.get('https'):
        seo_flags.append(True)
    
    # CDN/WAF
    if donnees.get('cdn') or donnees.get('has_cdn'):
        seo_flags.append(True)
    
    # CMS reconnu
    cms = donnees.get('cms') or donnees.get('ecommerce')
    high_value_cms = {"WordPress", "WooCommerce", "PrestaShop", "Magento", "Joomla", "Drupal", "OpenCart"}
    if cms and cms in high_value_cms:
        seo_flags.append(True)
    
    # Technologies modernes
    techs = donnees.get('technologies', [])
    if techs:
        modern_tech = any(t in str(techs).lower() for t in ["analytics", "gtm", "google tag", "facebook pixel"])
        if modern_tech:
            seo_flags.append(True)
    
    # Score basé sur le nombre de flags positifs (max 4 flags = 100%)
    return round((len(seo_flags) / 4) * 100) if seo_flags else 50


def fix_scores(limit: int = None, source_filter: str = None, dry_run: bool = False):
    """
    Corrige les scores dans leads_audites et met à jour le JSON donnees_audit si nécessaire.
    """
    from database.connection import get_conn
    
    sniper_sources = ['ads', 'fb_ads', 'transparency', 'tech', 'ecom', 'jobs', 'bodacc']
    
    with get_conn() as conn:
        placeholders = ','.join('?' * len(sniper_sources))
        query = f"""
            SELECT lb.id, lb.source, lb.nom, lb.donnees_audit,
                   la.id as audit_id, la.mobile_score, 
                   la.desktop_score, la.score_seo, la.email_objet, la.email_corps
            FROM leads_bruts lb
            JOIN leads_audites la ON la.lead_id = lb.id
            WHERE lb.source IN ({placeholders})
              AND la.template_used = 'sniper'
        """
        params = list(sniper_sources)
        
        if source_filter:
            query = query.replace(f"lb.source IN ({placeholders})", "lb.source = ?")
            params = [source_filter]
        
        query += " ORDER BY lb.id DESC"
        
        if limit:
            query += f" LIMIT {limit}"
        
        rows = conn.execute(query, params).fetchall()
    
    logger.info(f"{len(rows)} leads Sniper à vérifier")
    
    if not rows:
        logger.info("Aucun lead à traiter.")
        return
    
    stats = {
        'total': len(rows),
        'db_updated': 0,
        'json_updated': 0,
        'already_ok': 0,
        'failed': 0,
    }
    
    for row in rows:
        lead_id = row['id']
        source = row['source']
        nom = row['nom']
        audit_id = row['audit_id']
        
        donnees = parse_donnees_audit(row['donnees_audit'])
        
        # Valeurs actuelles
        db_desktop = row['desktop_score']
        db_seo = row['score_seo']
        db_mobile = row['mobile_score']
        
        # Valeurs disponibles
        json_desktop = donnees.get('score_desktop') or donnees.get('desktop_score')
        json_mobile = donnees.get('score_mobile') or donnees.get('mobile_score')
        
        # Déterminer les nouvelles valeurs
        new_desktop = json_desktop if json_desktop else (json_mobile if json_mobile else db_mobile)
        new_seo = donnees.get('score_seo') or calculate_score_seo(donnees)
        
        needs_db_update = (db_desktop == 0 or db_desktop is None) and new_desktop
        needs_db_update = needs_db_update or ((db_seo == 0 or db_seo is None) and new_seo)
        
        needs_json_update = not donnees.get('score_seo') and new_seo
        
        if not needs_db_update and not needs_json_update:
            stats['already_ok'] += 1
            continue
        
        logger.info(f"\n[{lead_id}] {nom} ({source})")
        
        if needs_db_update:
            logger.info(f"  DB: desktop {db_desktop} → {new_desktop}, seo {db_seo} → {new_seo}")
        
        if dry_run:
            logger.info("  [DRY RUN] Simulation")
            continue
        
        try:
            with get_conn() as conn:
                # Mise à jour des scores en DB
                if needs_db_update:
                    conn.execute("""
                        UPDATE leads_audites 
                        SET desktop_score = ?, score_seo = ?
                        WHERE id = ?
                    """, (new_desktop or db_desktop or 0, new_seo or db_seo or 50, audit_id))
                
                # Mise à jour du JSON donnees_audit si score_seo manquant
                if needs_json_update:
                    donnees['score_seo'] = new_seo
                    if not donnees.get('score_desktop') and new_desktop:
                        donnees['score_desktop'] = new_desktop
                    
                    conn.execute("""
                        UPDATE leads_bruts 
                        SET donnees_audit = ?
                        WHERE id = ?
                    """, (json.dumps(donnees, ensure_ascii=False), lead_id))
                
                conn.commit()
            
            stats['db_updated'] += 1
            if needs_json_update:
                stats['json_updated'] += 1
                
        except Exception as e:
            stats['failed'] += 1
            logger.error(f"  ✗ Erreur DB: {e}")
    
    logger.info("\n" + "="*60)
    logger.info("RÉSUMÉ DE LA CORRECTION")
    logger.info("="*60)
    logger.info(f"Total vérifiés: {stats['total']}")
    logger.info(f"Déjà corrects: {stats['already_ok']}")
    logger.info(f"DB mis à jour: {stats['db_updated']}")
    logger.info(f"JSON mis à jour: {stats['json_updated']}")
    logger.info(f"Échecs: {stats['failed']}")
    
    return stats


def show_preview(limit: int = 20, source_filter: str = None):
    """Affiche les leads qui seront affectés."""
    from database.connection import get_conn
    
    sniper_sources = ['ads', 'fb_ads', 'transparency', 'tech', 'ecom', 'jobs', 'bodacc']
    placeholders = ','.join('?' * len(sniper_sources))
    
    query = f"""
        SELECT lb.id, lb.source, lb.nom, lb.donnees_audit,
               la.desktop_score, la.score_seo, la.email_objet
        FROM leads_bruts lb
        JOIN leads_audites la ON la.lead_id = lb.id
        WHERE lb.source IN ({placeholders})
          AND la.template_used = 'sniper'
        ORDER BY lb.id DESC
        LIMIT ?
    """
    
    params = sniper_sources + [limit]
    
    if source_filter:
        query = query.replace(f"lb.source IN ({placeholders})", "lb.source = ?")
        params = [source_filter, limit]
    
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    
    print(f"\n{'ID':<6} {'Source':<10} {'Desktop':<8} {'SEO':<6} {'Nom'}")
    print("-" * 80)
    
    needs_fix_count = 0
    
    for row in rows:
        donnees = parse_donnees_audit(row['donnees_audit'])
        
        db_desktop = row['desktop_score'] or 0
        db_seo = row['score_seo'] or 0
        
        json_desktop = donnees.get('score_desktop') or donnees.get('desktop_score') or 0
        json_mobile = donnees.get('score_mobile') or donnees.get('mobile_score') or 0
        json_seo = donnees.get('score_seo') or 0
        
        calc_seo = calculate_score_seo(donnees)
        
        needs_fix = (db_desktop == 0 and (json_desktop > 0 or json_mobile > 0)) or \
                    (db_seo == 0 and (json_seo > 0 or calc_seo > 0))
        
        marker = " <<< FIX" if needs_fix else ""
        if needs_fix:
            needs_fix_count += 1
        
        print(f"{row['id']:<6} {row['source']:<10} {db_desktop:<8} {db_seo:<6} "
              f"{row['nom'][:35]}{marker}")
        
        if needs_fix:
            print(f"       JSON: desktop={json_desktop}, mobile={json_mobile}, "
                  f"seo_json={json_seo}, seo_calc={calc_seo}")
    
    print(f"\n{len(rows)} leads affichés, {needs_fix_count} nécessitent une correction")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Correction des scores Sniper")
    parser.add_argument("--limit", type=int, default=100, help="Nombre max de leads")
    parser.add_argument("--source", type=str, choices=['ads', 'tech', 'jobs', 'bodacc', 'ecom'],
                        help="Filtrer par source")
    parser.add_argument("--dry-run", action="store_true", 
                        help="Mode simulation (ne pas modifier)")
    parser.add_argument("--preview", action="store_true",
                        help="Afficher les leads affectés sans modifier")
    
    args = parser.parse_args()
    
    if args.preview:
        show_preview(args.limit, args.source)
    else:
        print("Mode: correction des scores")
        print("Utilisez --preview pour voir les leads affectés")
        print("Utilisez --dry-run pour simuler sans modifier")
        print()
        fix_scores(args.limit, args.source, args.dry_run)
