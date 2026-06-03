# -*- coding: utf-8 -*-
import sqlite3
import os

def main():
    db_path = 'data/prospection.db'
    if not os.path.exists(db_path):
        db_path = '../data/prospection.db'
        
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    # 1. Total count of approved leads
    cur1 = conn.execute("SELECT COUNT(*) as c FROM leads_audites WHERE approuve = 1")
    approuve_total = cur1.fetchone()['c']
    print(f"Total approved leads (approuve = 1) in database: {approuve_total}")
    
    # 2. Approved leads grouped by statut_prospection
    cur2 = conn.execute("""
        SELECT statut_prospection, COUNT(*) as c 
        FROM leads_audites 
        WHERE approuve = 1 
        GROUP BY statut_prospection
    """)
    print("\n=== APPROVED LEADS BY STATUT PROSPECTION ===")
    rows2 = cur2.fetchall()
    if rows2:
        for r in rows2:
            print(f"Statut Prospection: {r['statut_prospection']:<15} | Count: {r['c']}")
    else:
        print("No approved leads found.")
        
    # 3. Non-approved leads that have emails generated
    cur3 = conn.execute("""
        SELECT statut_prospection, COUNT(*) as c 
        FROM leads_audites 
        WHERE approuve = 0 
          AND email_corps IS NOT NULL 
          AND email_corps != ''
        GROUP BY statut_prospection
    """)
    print("\n=== UNAPPROVED LEADS WITH GENERATED EMAILS ===")
    rows3 = cur3.fetchall()
    for r in rows3:
        print(f"Statut Prospection: {r['statut_prospection']:<15} | Count: {r['c']}")

if __name__ == '__main__':
    main()
