# -*- coding: utf-8 -*-
import sqlite3
import os

def main():
    db_path = 'data/prospection.db'
    if not os.path.exists(db_path):
        db_path = '../data/prospection.db'
        
    conn = sqlite3.connect(db_path)
    
    # 1. Find the lead ID by email
    email = "info@smile2impress.com"
    cur = conn.execute("SELECT id, nom FROM leads_bruts WHERE email = ?", (email,))
    row = cur.fetchone()
    
    if not row:
        print(f"Lead with email '{email}' not found.")
        return
        
    lead_id = row[0]
    company_name = row[1]
    print(f"Found lead to fix:")
    print(f"  Lead ID:      {lead_id}")
    print(f"  Company Name: {company_name}")
    
    # 2. Mark as unapproved in leads_audites so it is skipped
    conn.execute("UPDATE leads_audites SET approuve = 0 WHERE lead_id = ?", (lead_id,))
    conn.commit()
    
    print("\n[SUCCESS] Set 'approuve = 0' for this lead. It will be safely skipped during the sending batch!")

if __name__ == '__main__':
    main()
