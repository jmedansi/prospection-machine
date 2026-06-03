# -*- coding: utf-8 -*-
import sqlite3
import os

def main():
    db_path = 'data/prospection.db'
    if not os.path.exists(db_path):
        db_path = '../data/prospection.db'
        
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    # Select leads that have generated emails but are stuck in 'en_attente'
    cur = conn.execute("""
        SELECT lb.id, lb.nom, lb.site_web, la.email_objet
        FROM leads_bruts lb
        JOIN leads_audites la ON la.lead_id = lb.id
        WHERE lb.statut = 'en_attente'
          AND (lb.source LIKE '%ads%' OR lb.source LIKE '%google%')
          AND la.email_corps IS NOT NULL
          AND la.email_corps != ''
    """)
    rows = [dict(r) for r in cur.fetchall()]
    
    print(f"Found {len(rows)} Google Ads leads that have generated emails but are stuck in 'en_attente' status.")
    
    if len(rows) == 0:
        print("No leads to sync.")
        return
        
    success_count = 0
    for r in rows:
        print(f"Syncing ID: {r['id']} | {r['nom']} -> 'email_genere'")
        conn.execute("UPDATE leads_bruts SET statut = 'email_genere' WHERE id = ?", (r['id'],))
        success_count += 1
        
    conn.commit()
    print(f"\nSuccessfully transitioned {success_count} leads to 'email_genere' status.")

if __name__ == '__main__':
    main()
