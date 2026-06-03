# -*- coding: utf-8 -*-
import sys
import os

# Add project root to sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.sniper_sender_service import send_sniper_step1
from database.connection import get_conn

def main():
    print("=== SNIPER STEP 1 DRY RUN ===")
    # 1. Run dry run to see what would happen
    dry_run_stats = send_sniper_step1(dry_run=True)
    print(f"Dry Run Stats: {dry_run_stats}")
    
    # 2. Print details of the top 5 approved leads that are ready
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT la.id, la.email_valide, la.email_objet, lb.nom as company_nom
            FROM leads_audites la
            JOIN leads_bruts lb ON lb.id = la.lead_id
            WHERE la.statut_prospection = 'a_contacter'
              AND la.approuve = 1
              AND la.email_valide IS NOT NULL AND la.email_valide != ''
              AND la.email_corps IS NOT NULL AND la.email_corps != ''
              AND lb.source IN ('ads', 'fb_ads', 'ecom', 'tech', 'jobs', 'bodacc')
            ORDER BY la.score_urgence DESC
            LIMIT 5
        """).fetchall()
        
    if not rows:
        print("\nNo approved leads ready to send in the database.")
        return
        
    print(f"\n=== TOP 5 LEADS READY IN SENDING QUEUE ===")
    for idx, row in enumerate(rows, 1):
        print(f"{idx}. Company: {row['company_nom'][:25]:<25} | Email: {row['email_valide']:<30} | Subject: {row['email_objet']}")

if __name__ == '__main__':
    main()
