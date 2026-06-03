# -*- coding: utf-8 -*-
import sqlite3
import os

def main():
    db_path = 'data/prospection.db'
    if not os.path.exists(db_path):
        db_path = '../data/prospection.db'
        
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    cur = conn.execute("""
        SELECT lb.id, lb.nom, lb.site_web, lb.source, la.email_corps
        FROM leads_bruts lb
        LEFT JOIN leads_audites la ON la.lead_id = lb.id
        WHERE lb.statut = 'en_attente'
          AND (lb.source LIKE '%ads%' OR lb.source LIKE '%google%')
    """)
    for r in cur.fetchall():
        has_email = "Yes" if r['email_corps'] else "No"
        print(f"ID: {r['id']} | Nom: {r['nom']} | Site: {r['site_web']} | Source: {r['source']} | Has Email: {has_email}")

if __name__ == '__main__':
    main()
