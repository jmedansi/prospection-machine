# -*- coding: utf-8 -*-
import sqlite3
import os
import json

def main():
    db_path = 'data/prospection.db'
    if not os.path.exists(db_path):
        db_path = '../data/prospection.db'
        
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    cur = conn.execute("""
        SELECT id, nom, site_web, source, statut, tag_urgence, niveau_urgence, 
               donnees_audit IS NULL as audit_is_null
        FROM leads_bruts 
        WHERE statut='en_attente' AND (source LIKE '%ads%' OR source LIKE '%google%')
    """)
    rows = cur.fetchall()
    print(f"Total remaining pending ads/google leads in database: {len(rows)}")
    
    # Show status breakdown of all remaining
    null_count = sum(1 for r in rows if r['audit_is_null'])
    not_null_count = len(rows) - null_count
    print(f"  Audit is NULL (needs auditing): {null_count}")
    print(f"  Audit is NOT NULL (already audited): {not_null_count}")
    
    # Print a few of the NOT NULL ones to see what is in them
    not_null_leads = [r for r in rows if not r['audit_is_null']]
    if not_null_leads:
        print("\nExamples of already audited pending leads:")
        for r in not_null_leads[:5]:
            print(f"ID: {r['id']} | {r['nom']} | Source: {r['source']} | Tag: {r['tag_urgence']} | Nv: {r['niveau_urgence']}")

if __name__ == '__main__':
    main()
