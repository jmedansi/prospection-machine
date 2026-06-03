# -*- coding: utf-8 -*-
import sqlite3
import os

def main():
    db_path = 'data/prospection.db'
    if not os.path.exists(db_path):
        db_path = '../data/prospection.db'
        
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    print("=== VERIFYING LEAD STATUS TRANSITIONS ===")
    
    # Let's count how many leads are in each status today (among those sent)
    cur = conn.execute("""
        SELECT lb.statut, la.statut_prospection, COUNT(*) as count
        FROM leads_bruts lb
        JOIN leads_audites la ON la.lead_id = lb.id
        JOIN emails_envoyes ee ON ee.lead_id = lb.id
        WHERE ee.date_envoi LIKE '2026-05-18%'
        GROUP BY lb.statut, la.statut_prospection
    """)
    rows = cur.fetchall()
    if rows:
        print("\n=== STATUS OF TODAY'S SENT LEADS IN DATABASE ===")
        for r in rows:
            print(f"leads_bruts.statut:         '{r['statut']}'")
            print(f"leads_audites.statut_prospection: '{r['statut_prospection']}'")
            print(f"Count of Leads:             {r['count']}")
            print("-" * 50)
    else:
        print("No matches found in sent emails join.")

if __name__ == '__main__':
    main()
