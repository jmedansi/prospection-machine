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
    
    print("=== ADS LEADS STATE ===")
    cur1 = conn.execute(
        "SELECT statut, COUNT(*) as count FROM leads_bruts WHERE (source LIKE '%ads%' OR source LIKE '%google%') GROUP BY statut"
    )
    for r in cur1.fetchall():
        print(f"Statut: {r['statut']:<15} | Count: {r['count']}")
        
    print("\n=== TOP 15 RECENTLY AUDITED ADS LEADS ===")
    cur2 = conn.execute("""
        SELECT lb.id, lb.nom, lb.site_web, lb.statut, lb.tag_urgence, lb.niveau_urgence, la.date_audit
        FROM leads_bruts lb
        LEFT JOIN leads_audites la ON la.lead_id = lb.id
        WHERE (lb.source LIKE '%ads%' or lb.source LIKE '%google%') AND (lb.donnees_audit IS NOT NULL OR lb.statut = 'archive')
        ORDER BY lb.id DESC LIMIT 15
    """)
    for r in cur2.fetchall():
        tag = r['tag_urgence'] or 'Filtré/Wix/Rapide'
        date_aud = r['date_audit'] or 'N/A (archivé)'
        print(f"ID: {r['id']} | Nom: {r['nom'][:25]:<25} | Statut: {r['statut']:<12} | Urgence: {tag:<20} (nv {r['niveau_urgence'] or 0}) | Date: {date_aud}")

if __name__ == '__main__':
    main()
