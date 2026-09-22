# -*- coding: utf-8 -*-
"""
tools/audit_pending_ads_leads.py

Script to audit pending Google Ads leads.
It performs:
1. Deep Playwright performance measurement (mobile & desktop LCP, FCP).
2. PageSpeed Qualitatif (SEO, accessibility, best practices).
3. Technology stack analysis (via Wappalyzer and fallback BeautifulSoup).
4. Qualification and Scoring (High-ticket score_lead).
5. Auto-rejection of leads with no urgency or low-code CMS (Wix, Jimdo).
6. Insertion/update of the audit data and generation of personalized B2B email sequence.
"""

import sys
import os
import sqlite3
import json
import asyncio
import logging
import argparse

# Force UTF-8 console output for Windows
if sys.stdout.encoding.lower() != 'utf-8':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

# Add project root to sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from database.connection import get_conn
from database import update_lead_statut
from auditeur.agents.web_analyzer import run_web_analysis
from scraper.sniper.wappalyzer_runner import analyze as wappalyzer_analyze
from scraper.sniper.scoring import score_lead, build_donnees_audit
from sniper.email_generator import generate_sniper_email_for_lead
from core.browser import close_all_browsers_sync

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('audit_pending_ads')

async def audit_lead(lead: dict) -> bool:
    lead_id = lead['id']
    nom = lead.get('nom', '') or 'Inconnu'
    site_url = lead.get('site_web', '')
    
    logger.info(f"\n==================================================")
    logger.info(f"AUDITING LEAD [{lead_id}]: {nom}")
    logger.info(f"Website: {site_url}")
    logger.info(f"==================================================")
    
    if not site_url or not site_url.startswith(('http://', 'https://')):
        logger.warning(f"URL invalide ou absente pour le lead {lead_id} ({site_url}) -> Rejet")
        update_lead_statut(lead_id, 'archive')
        return False
        
    try:
        # Step 1: Playwright real web analysis + PageSpeed qualitative
        logger.info("Step 1: Running Playwright headless speed measurement & PageSpeed SEO...")
        web_data = await run_web_analysis(site_url)
        
        # Step 2: Wappalyzer analysis
        logger.info("Step 2: Detecting technology stack (Wappalyzer & BeautifulSoup)...")
        wappalyzer_data = wappalyzer_analyze(site_url)
        
        # Merge BeautifulSoup fallback CMS into Wappalyzer CMS if Wappalyzer didn't detect any
        if not wappalyzer_data.get('cms') and web_data.get('cms_detected'):
            detected = web_data['cms_detected'].title()
            logger.info(f"  -> Using BeautifulSoup fallback CMS detection: {detected}")
            wappalyzer_data['cms'] = detected
            
        # Step 3: High-ticket qualification & scoring
        logger.info("Step 3: Calculating B2B urgency score...")
        score = score_lead(web_data, wappalyzer_data, source="ads")
        
        if score is None:
            logger.info(f"  ❌ Lead REJECTED: Site is fast or uses a low-code CMS (Wix/Jimdo). Archiving lead...")
            update_lead_statut(lead_id, 'archive')
            return False
            
        tag, niveau, reason = score
        logger.info(f"  ✓ Lead QUALIFIED: tag={tag}, niveau={niveau}, reason={reason}")
        
        # Step 4: Build donnees_audit JSON and update leads_bruts
        logger.info("Step 4: Storing audit results in database...")
        # Prepare enriched dict for build_donnees_audit
        enriched_data = {
            "has_https": web_data.get("has_https", True),
            "telephone": lead.get("telephone"),
            "email_valide": lead.get("email_valide") or lead.get("email"),
            "email_source": "scraped"
        }
        donnees_audit_json = build_donnees_audit(web_data, wappalyzer_data, tag, niveau, reason, enriched_data)
        
        with get_conn() as conn:
            conn.execute("""
                UPDATE leads_bruts
                SET tag_urgence = ?,
                    niveau_urgence = ?,
                    donnees_audit = ?
                WHERE id = ?
            """, (tag, niveau, donnees_audit_json, lead_id))
            conn.commit()
            
        # Step 5: Generate sniper email & publish HTML report to Vercel
        logger.info("Step 5: Generating B2B copywriting email sequence & publishing HTML report...")
        email_ok = generate_sniper_email_for_lead(lead_id)
        if email_ok:
            logger.info(f"  ✓ [SUCCESS] Email generated and report published for {nom}!")
            return True
        else:
            logger.error(f"  ❌ [ERROR] Failed to generate email or report for {nom}")
            return False
            
    except Exception as e:
        logger.exception(f"Exception during audit of lead {lead_id} ({nom}): {e}")
        return False

async def main_async(limit: int = None):
    # Fetch all pending google ads leads without audit data
    with get_conn() as conn:
        cursor = conn.execute("""
            SELECT * FROM leads_bruts
            WHERE statut = 'en_attente'
              AND (source LIKE '%ads%' OR source LIKE '%google%')
              AND donnees_audit IS NULL
            ORDER BY id DESC
        """)
        leads = [dict(r) for r in cursor.fetchall()]
        
    total = len(leads)
    logger.info(f"Found {total} pending Google Ads leads with no audit data.")
    
    if total == 0:
        logger.info("No leads to audit. Exiting.")
        return
        
    if limit is not None:
        leads = leads[:limit]
        logger.info(f"Limited run to top {limit} leads.")
        
    success_count = 0
    processed_count = 0
    
    for lead in leads:
        processed_count += 1
        logger.info(f"\nProcessing lead {processed_count}/{len(leads)}...")
        ok = await audit_lead(lead)
        if ok:
            success_count += 1
            
        # Optional: brief sleep between leads
        await asyncio.sleep(1.0)
        
    logger.info(f"\n==================================================")
    logger.info(f"AUDIT RUN COMPLETED")
    logger.info(f"Processed: {processed_count}")
    logger.info(f"Successful: {success_count} leads qualified & emails generated")
    logger.info(f"==================================================")

def main():
    parser = argparse.ArgumentParser(description="Audit and generate emails for pending Google Ads leads.")
    parser.add_argument("--limit", type=int, default=None, help="Max number of leads to audit in this run.")
    args = parser.parse_args()
    
    try:
        asyncio.run(main_async(args.limit))
    finally:
        # Clean up Playwright browsers
        try:
            close_all_browsers_sync()
        except:
            pass

if __name__ == '__main__':
    main()
