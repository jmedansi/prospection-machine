# -*- coding: utf-8 -*-
"""
Script de ré-audit PageSpeed pour les leads Sniper existants
Récupère les VRAIES données de PageSpeed (mobile + desktop) et met à jour la DB.

Usage:
    python sniper_reaudit_pagespeed.py --preview --limit 30     # Voir les leads concernés
    python sniper_reaudit_pagespeed.py --dry-run --limit 5      # Simulation
    python sniper_reaudit_pagespeed.py --limit 50               # Exécution réelle
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


def run_real_pagespeed_audit(url: str) -> Dict:
    """
    Lance un vrai audit PageSpeed Insights pour mobile ET desktop.
    Retourne un dict avec les vraies métriques.
    """
    try:
        from auditeur.agents.web_analyzer import run_pagespeed
        
        logger.info(f"    → Appel PageSpeed API pour {url}...")
        
        # Audit mobile
        mobile_result = run_pagespeed(url, strategy="mobile")
        
        # Audit desktop
        desktop_result = run_pagespeed(url, strategy="desktop")
        
        # Fusionner les résultats
        result = {
            **mobile_result,
            **desktop_result,
        }
        
        # Compatibilité avec les anciens noms de champs
        if 'mobile_score' in result:
            result['score_mobile'] = result['mobile_score']
        if 'desktop_score' in result:
            result['score_desktop'] = result['desktop_score']
        if 'mobile_lcp_ms' in result:
            result['lcp_ms'] = result['mobile_lcp_ms']
        if 'mobile_fcp_ms' in result:
            result['fcp_ms'] = result['mobile_fcp_ms']
        
        logger.info(f"    ✓ Mobile: {result.get('mobile_score', 'N/A')}/100, "
                   f"Desktop: {result.get('desktop_score', 'N/A')}/100, "
                   f"LCP: {result.get('mobile_lcp_ms', 'N/A')}ms")
        
        return result
        
    except Exception as e:
        logger.error(f"    ✗ Erreur PageSpeed pour {url}: {e}")
        return {}


def reaudit_leads(limit: int = None, source_filter: str = None, dry_run: bool = False):
    """
    Relance les audits PageSpeed pour les leads Sniper existants.
    Met à jour leads_bruts.donnees_audit et leads_audites.
    """
    from database.connection import get_conn
    
    sniper_sources = ['ads', 'fb_ads', 'transparency', 'tech', 'ecom', 'jobs', 'bodacc']
    
    with get_conn() as conn:
        placeholders = ','.join('?' * len(sniper_sources))
        query = f"""
            SELECT lb.id, lb.source, lb.nom, lb.site_web, lb.donnees_audit,
                   la.id as audit_id, la.mobile_score, la.desktop_score, la.score_seo
            FROM leads_bruts lb
            JOIN leads_audites la ON la.lead_id = lb.id
            WHERE lb.source IN ({placeholders})
              AND la.template_used = 'sniper'
              AND lb.site_web IS NOT NULL
              AND lb.site_web != ''
        """
        params = list(sniper_sources)
        
        if source_filter:
            query = query.replace(f"lb.source IN ({placeholders})", "lb.source = ?")
            params = [source_filter]
        
        query += " ORDER BY lb.id DESC"
        
        if limit:
            query += f" LIMIT {limit}"
        
        rows = conn.execute(query, params).fetchall()
    
    logger.info(f"{len(rows)} leads Sniper à ré-auditer")
    
    if not rows:
        logger.info("Aucun lead à traiter.")
        return
    
    stats = {
        'total': len(rows),
        'success': 0,
        'failed': 0,
        'skipped': 0,
    }
    
    for row in rows:
        lead_id = row['id']
        source = row['source']
        nom = row['nom']
        site_web = row['site_web']
        audit_id = row['audit_id']
        
        logger.info(f"\n[{lead_id}] {nom} ({source})")
        logger.info(f"  Site: {site_web}")
        
        if not site_web.startswith(('http://', 'https://')):
            logger.warning(f"  ⚠ URL invalide, ignoré")
            stats['skipped'] += 1
            continue
        
        if dry_run:
            logger.info("  [DRY RUN] Simulation - pas d'appel API")
            stats['skipped'] += 1
            continue
        
        # Lancer le vrai audit PageSpeed
        audit_result = run_real_pagespeed_audit(site_web)
        
        if not audit_result:
            stats['failed'] += 1
            continue
        
        # Récupérer les anciennes données
        donnees = parse_donnees_audit(row['donnees_audit'])
        
        # Mettre à jour avec les nouvelles valeurs réelles
        donnees['score_mobile'] = audit_result.get('mobile_score') or audit_result.get('score_mobile')
        donnees['score_desktop'] = audit_result.get('desktop_score') or audit_result.get('score_desktop')
        donnees['lcp_ms'] = audit_result.get('mobile_lcp_ms') or audit_result.get('lcp_ms')
        donnees['fcp_ms'] = audit_result.get('mobile_fcp_ms') or audit_result.get('fcp_ms')
        donnees['page_size_kb'] = audit_result.get('mobile_page_size_kb')
        donnees['render_blocking_scripts'] = audit_result.get('mobile_render_blocking')
        
        # Calculer le score SEO si pas présent
        if not donnees.get('score_seo'):
            # Utiliser les données wappalyzer existantes
            score_seo = 50  # Valeur par défaut
            if donnees.get('cdn') or donnees.get('has_cdn'):
                score_seo = 75
            donnees['score_seo'] = score_seo
        
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
                """, (
                    donnees.get('score_mobile') or donnees.get('mobile_score'),
                    donnees.get('score_desktop') or donnees.get('desktop_score'),
                    donnees.get('score_seo'),
                    donnees.get('lcp_ms'),
                    audit_id
                ))
                
                conn.commit()
            
            stats['success'] += 1
            logger.info(f"  ✓ Scores mis à jour: "
                       f"mobile={donnees.get('score_mobile', 'N/A')}, "
                       f"desktop={donnees.get('score_desktop', 'N/A')}, "
                       f"seo={donnees.get('score_seo', 'N/A')}")
            
        except Exception as e:
            stats['failed'] += 1
            logger.error(f"  ✗ Erreur DB: {e}")
    
    logger.info("\n" + "="*60)
    logger.info("RÉSUMÉ DU RÉ-AUDIT PAGE SPEED")
    logger.info("="*60)
    logger.info(f"Total traités: {stats['total']}")
    logger.info(f"Succès: {stats['success']}")
    logger.info(f"Échecs: {stats['failed']}")
    logger.info(f"Ignorés: {stats['skipped']}")
    
    return stats


def show_preview(limit: int = 20, source_filter: str = None):
    """Affiche les leads qui seront ré-audités."""
    from database.connection import get_conn
    
    sniper_sources = ['ads', 'fb_ads', 'transparency', 'tech', 'ecom', 'jobs', 'bodacc']
    placeholders = ','.join('?' * len(sniper_sources))
    
    query = f"""
        SELECT lb.id, lb.source, lb.nom, lb.site_web,
               la.mobile_score, la.desktop_score, la.score_seo
        FROM leads_bruts lb
        JOIN leads_audites la ON la.lead_id = lb.id
        WHERE lb.source IN ({placeholders})
          AND la.template_used = 'sniper'
          AND lb.site_web IS NOT NULL
          AND lb.site_web != ''
        ORDER BY lb.id DESC
        LIMIT ?
    """
    
    params = sniper_sources + [limit]
    
    if source_filter:
        query = query.replace(f"lb.source IN ({placeholders})", "lb.source = ?")
        params = [source_filter, limit]
    
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    
    print(f"\n{'ID':<6} {'Source':<10} {'Mobile':<8} {'Desktop':<8} {'Site'}")
    print("-" * 90)
    
    for row in rows:
        mobile = row['mobile_score'] or 0
        desktop = row['desktop_score'] or 0
        
        needs_audit = desktop == 0
        marker = " <<< RÉ-AUDIT" if needs_audit else ""
        
        site_display = row['site_web'][:50] if row['site_web'] else 'N/A'
        print(f"{row['id']:<6} {row['source']:<10} {mobile:<8} {desktop:<8} {site_display}{marker}")
    
    print(f"\n{len(rows)} leads affichés")
    print(f"\nNote: Chaque ré-audit fait 2 appels API (mobile + desktop)")
    print(f"Quota PageSpeed: 25 requêtes/jour sans clé API, 100+ avec clé")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ré-audit PageSpeed pour leads Sniper")
    parser.add_argument("--limit", type=int, default=None, help="Nombre max de leads (défaut: tous)")
    parser.add_argument("--source", type=str, choices=['ads', 'tech', 'jobs', 'bodacc', 'ecom'],
                        help="Filtrer par source")
    parser.add_argument("--dry-run", action="store_true", 
                        help="Mode simulation (ne pas appeler l'API)")
    parser.add_argument("--preview", action="store_true",
                        help="Afficher les leads concernés sans ré-auditer")
    
    args = parser.parse_args()
    
    if args.preview:
        show_preview(args.limit or 50, args.source)
    else:
        print("⚠️  ATTENTION: Ce script fait des appels API PageSpeed.")
        print("Quota: 25/jour sans clé API, 100+/jour avec clé")
        print("Utilisez --preview pour voir les leads, --dry-run pour simuler")
        print()
        
        if not args.dry_run:
            confirm = input("Continuer avec les vrais appels API ? (oui/non): ")
            if confirm.lower() != 'oui':
                print("Annulé.")
                sys.exit(0)
        
        reaudit_leads(args.limit, args.source, args.dry_run)
