# -*- coding: utf-8 -*-
import sqlite3
import os

def main():
    db_path = 'data/prospection.db'
    if not os.path.exists(db_path):
        db_path = '../data/prospection.db'
        
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    cur = conn.execute("SELECT * FROM leads_audites WHERE lead_id = 2252")
    row = cur.fetchone()
    if row:
        d = dict(row)
        print("=== GENERATED EMAIL DETAILS ===")
        print(f"Lead ID: {d['lead_id']}")
        print(f"Subject: {d['email_objet']}")
        print(f"Profile: {d['profile']}")
        print(f"Lien Rapport: {d['lien_rapport']}")
        print(f"Urgence: {d['score_urgence']}")
        print(f"Template Used: {d['template_used']}")
        print("\n=== EMAIL BODY PREVIEW (first 400 chars) ===")
        print(d['email_corps'][:400])
    else:
        print("No audit row found in leads_audites for lead 2252!")

if __name__ == '__main__':
    main()
