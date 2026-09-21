# -*- coding: utf-8 -*-
"""
Script complet de ré-audit et régénération des emails Sniper

Usage:
    python sniper_full_regen.py --dry-run     # Simulation
    python sniper_full_regen.py               # Exécution réelle
    python sniper_full_regen.py --limit 20    # Limiter à 20 leads
"""

import argparse
import json
import logging
import sys
import os
import time
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


def run_full_pagespeed_audit(url: str) -> Dict:
    """
    Lance un audit PageSpeed complet pour mobile ET desktop.
    Retourne un dict avec toutes les métriques.
    """
    try:
        from auditeur.agents.web_analyzer import run_pagespeed
        
        logger.info(f"    → Audit PageSpeed: {url}")
        
        # Audit mobile
        mobile_result = run_pagespeed(url, strategy="mobile")
        time.sleep(1)  # Petit délai entre les appels
        
        # Audit desktop
        desktop_result = run_pagespeed(url, strategy="desktop")
        
        # Fusionner les résultats
        result = {**mobile_result, **desktop_result}
        
        # Compatibilité avec les anciens noms de champs
        if 'mobile_score' in result:
            result['score_mobile'] = result['mobile_score']
        if 'desktop_score' in result:
            result['score_desktop'] = result['desktop_score']
        if 'mobile_lcp_ms' in result:
            result['lcp_ms'] = result['mobile_lcp_ms']
        if 'mobile_fcp_ms' in result:
            result['fcp_ms'] = result['mobile_fcp_ms']
        if 'mobile_seo_score' in result:
            result['score_seo'] = result['mobile_seo_score']
        
        logger.info(f"    ✓ Mobile: {result.get('mobile_score', 'N/A')}/100, "
                   f"Desktop: {result.get('desktop_score', 'N/A')}/100, "
                   f"SEO: {result.get('score_seo', 'N/A')}/100")
        
        return result
        
    except Exception as e:
        logger.error(f"    ✗ Erreur PageSpeed pour {url}: {e}")
        return {}


def full_regen(limit: int = None, dry_run: bool = False):
    """
    Ré-audit complet + régénération des emails pour tous les leads Sniper.
    """
    from database.connection import get_conn
    from sniper.email_generator import generate_sniper_email_for_lead
    
    sniper_sources = ['ads', 'fb_ads', 'transparency', 'tech', 'ecom', 'jobs', 'bodacc']
    
    with get_conn() as conn:
        placeholders = ','.join('?' * len(sniper_sources))
        query = f"""
            SELECT lb.id, lb.source, lb.nom, lb.site_web, lb.donnees_audit,
                   la.id as audit_id, la.mobile_score, la.desktop_score, 
                   la.score_seo, la.email_objet
            FROM leads_bruts lb
            JOIN leads_audites la ON la.lead_id = lb.id
            WHERE lb.source IN ({placeholders})
              AND la.template_used = 'sniper'
              AND lb.site_web IS NOT NULL
              AND lb.site_web != ''
            ORDER BY lb.id DESC
        """
        params = list(sniper_sources)
        
        if limit:
            query += f" LIMIT {limit}"
        
        rows = conn.execute(query, params).fetchall()
    
    total = len(rows)
    logger.info(f"=" * 70)
    logger.info(f"RÉ-AUDIT ET RÉGÉNÉRATION DES EMAILS SNIPER")
    logger.info(f"=" * 70)
    logger.info(f"Total leads à traiter: {total}")
    logger.info(f"Mode: {'SIMULATION' if dry_run else 'RÉEL'}")
    logger.info(f"=" * 70)
    
    if not rows:
        logger.info("Aucun lead à traiter.")
        return
    
    stats = {
        'total': total,
        'success': 0,
        'failed': 0,
        'skipped': 0,
        'desktop_fixed': 0,
        'seo_fixed': 0,
    }
    
    for i, row in enumerate(rows, 1):
        lead_id = row['id']
        source = row['source']
        nom = row['nom']
        site_web = row['site_web']
        audit_id = row['audit_id']
        
        logger.info(f"\n[{i}/{total}] [{lead_id}] {nom} ({source})")
        logger.info(f"  Site: {site_web}")
        
        if not site_web.startswith(('http://', 'https://')):
            logger.warning(f"  ⚠ URL invalide, ignoré")
            stats['skipped'] += 1
            continue
        
        # Anciennes valeurs
        old_desktop = row['desktop_score'] or 0
        old_seo = row['score_seo'] or 0
        
        if dry_run:
            logger.info(f"  [DRY RUN] Simulation - pas d'appel API")
            logger.info(f"  Ancien: desktop={old_desktop}, seo={old_seo}")
            stats['skipped'] += 1
            continue
        
        # Étape 1: Ré-audit PageSpeed
        logger.info(f"  → Ré-audit PageSpeed...")
        audit_result = run_full_pagespeed_audit(site_web)
        
        if not audit_result:
            logger.error(f"  ✗ Échec de l'audit")
            stats['failed'] += 1
            continue
        
        # Étape 2: Mettre à jour donnees_audit
        donnees = parse_donnees_audit(row['donnees_audit'])
        
        # Nouvelles valeurs depuis PageSpeed
        new_mobile = audit_result.get('mobile_score') or audit_result.get('score_mobile')
        new_desktop = audit_result.get('desktop_score') or audit_result.get('score_desktop')
        new_seo = audit_result.get('score_seo') or audit_result.get('mobile_seo_score')
        new_lcp = audit_result.get('mobile_lcp_ms') or audit_result.get('lcp_ms')
        new_fcp = audit_result.get('mobile_fcp_ms') or audit_result.get('fcp_ms')
        
        # Mettre à jour le JSON
        donnees['score_mobile'] = new_mobile
        donnees['score_desktop'] = new_desktop
        donnees['score_seo'] = new_seo
        donnees['lcp_ms'] = new_lcp
        donnees['fcp_ms'] = new_fcp
        
        logger.info(f"  → Mise à jour DB...")
        
        try:
            with get_conn() as conn:
                # Mettre à jour leads_bruts.donnees_audit
                conn.execute("""
                    UPDATE leads_bruts 
                    SET donnees_audit = ?
                    WHERE id = ?
                """, (json.dumps(donnees, ensure_ascii=False), lead_id))
                
                # Mettre à jour leads_audites avec les nouveaux scores
                conn.execute("""
                    UPDATE leads_audites 
                    SET mobile_score = ?,
                        desktop_score = ?,
                        score_seo = ?,
                        lcp_ms = ?
                    WHERE id = ?
                """, (new_mobile, new_desktop, new_seo, new_lcp, audit_id))
                
                conn.commit()
            
            # Étape 3: Supprimer l'ancien email et régénérer
            logger.info(f"  → Régénération de l'email...")
            
            with get_conn() as conn:
                # Supprimer l'ancien audit email
                conn.execute(
                    "DELETE FROM leads_audites WHERE id=?",
                    (audit_id,)
                )
                # Reset le statut
                conn.execute(
                    "UPDATE leads_bruts SET statut='en_attente' WHERE id=?",
                    (lead_id,)
                )
                conn.commit()
            
            # Régénérer l'email
            success = generate_sniper_email_for_lead(lead_id)
            
            if success:
                stats['success'] += 1
                if new_desktop and old_desktop == 0:
                    stats['desktop_fixed'] += 1
                if new_seo and old_seo == 0:
                    stats['seo_fixed'] += 1
                logger.info(f"  ✓ Email régénéré avec succès")
            else:
                stats['failed'] += 1
                logger.warning(f"  ✗ Échec de la régénération de l'email")
                
        except Exception as e:
            stats['failed'] += 1
            logger.error(f"  ✗ Erreur: {e}")
        
        # Petit délai entre chaque lead pour ne pas surcharger l'API
        time.sleep(2)
    
    # Résumé final
    logger.info("\n" + "=" * 70)
    logger.info("RÉSUMÉ FINAL")
    logger.info("=" * 70)
    logger.info(f"Total traités: {stats['total']}")
    logger.info(f"Succès: {stats['success']}")
    logger.info(f"Échecs: {stats['failed']}")
    logger.info(f"Ignorés: {stats['skipped']}")
    logger.info(f"Desktop scores corrigés: {stats['desktop_fixed']}")
    logger.info(f"SEO scores corrigés: {stats['seo_fixed']}")
    logger.info("=" * 70)
    
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ré-audit et régénération complète Sniper")
    parser.add_argument("--limit", type=int, help="Nombre max de leads (défaut: tous)")
    parser.add_argument("--dry-run", action="store_true", help="Mode simulation")
    
    args = parser.parse_args()
    
    if args.dry_run:
        print("⚠️  MODE SIMULATION - Aucune modification ne sera faite")
        print()
    else:
        print("⚠️  ATTENTION: Ce script va:")
        print("   1. Relancer les audits PageSpeed (mobile + desktop)")
        print("   2. Mettre à jour les scores dans la DB")
        print("   3. Régénérer tous les emails")
        print()
        confirm = input("Continuer ? (oui/non): ")
        if confirm.lower() != 'oui':
            print("Annulé.")
            sys.exit(0)
        print()
    
    full_regen(args.limit, args.dry_run)
