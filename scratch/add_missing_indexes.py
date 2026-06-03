# -*- coding: utf-8 -*-
import sqlite3
import os

def main():
    db_path = 'data/prospection.db'
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        return
        
    print(f"=== DATABASE INDEX OPTIMIZATION: {db_path} ===")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 1. Create index on emails_envoyes(lead_id) - prevents full table scans on JOINs and subqueries
        print("Creating index: idx_emails_lead_id on emails_envoyes(lead_id)...")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_emails_lead_id ON emails_envoyes(lead_id)")
        
        # 2. Create index on leads_bruts(source) - accelerates filtering leads by source
        print("Creating index: idx_leads_source_field on leads_bruts(source)...")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_source_field ON leads_bruts(source)")
        
        # 3. Create index on leads_bruts(campaign_id) - accelerates campaign-based queries
        print("Creating index: idx_leads_campaign_field on leads_bruts(campaign_id)...")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_campaign_field ON leads_bruts(campaign_id)")
        
        conn.commit()
        print("[SUCCESS] All performance indexes successfully created and committed!")
        
    except Exception as e:
        print(f"[ERROR] Failed to create database indexes: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    main()
