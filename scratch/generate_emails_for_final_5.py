# -*- coding: utf-8 -*-
import sys
import os
import sqlite3
import logging

# Force UTF-8 console output for Windows
if sys.stdout.encoding.lower() != 'utf-8':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

# Add project root to sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sniper.email_generator import generate_sniper_email_for_lead
from database.connection import get_conn

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def main():
    final_ids = [1779, 1783, 1864, 1899, 1947]
    print(f"=== GENERATING EMAILS FOR FINAL 5 LEADS WITH TEMP SOURCE MIGRATION: {final_ids} ===")
    
    success_count = 0
    with get_conn() as conn:
        for lead_id in final_ids:
            print(f"\nProcessing ID {lead_id}...")
            try:
                # Step 1: Temporarily set source to 'ads'
                conn.execute("UPDATE leads_bruts SET source = 'ads' WHERE id = ?", (lead_id,))
                conn.commit()
                
                # Step 2: Generate email
                ok = generate_sniper_email_for_lead(lead_id)
                
                # Step 3: Revert source back to 'maps,ads'
                conn.execute("UPDATE leads_bruts SET source = 'maps,ads' WHERE id = ?", (lead_id,))
                conn.commit()
                
                if ok:
                    print(f"  [SUCCESS] Email generated for lead {lead_id}.")
                    success_count += 1
                else:
                    print(f"  [FAILED] Failed to generate email for lead {lead_id}.")
            except Exception as e:
                print(f"  [ERROR] Error for lead {lead_id}: {e}")
                # Ensure we revert source on failure
                try:
                    conn.execute("UPDATE leads_bruts SET source = 'maps,ads' WHERE id = ?", (lead_id,))
                    conn.commit()
                except:
                    pass
            
    print(f"\n=== PROCESS COMPLETE: {success_count}/{len(final_ids)} successfully generated ===")

if __name__ == '__main__':
    main()
