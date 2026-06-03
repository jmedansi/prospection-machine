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
    
    print("=== INSPECTING LEAD 1592 IN LEADS_BRUTS ===")
    cur1 = conn.execute("SELECT * FROM leads_bruts WHERE id = 1592")
    row1 = cur1.fetchone()
    if row1:
        d1 = dict(row1)
        print(f"ID: {d1['id']} | Nom: {d1['nom']} | Statut: {d1['statut']} | Tag: {d1['tag_urgence']} | Nv: {d1['niveau_urgence']}")
        print(f"donnees_audit: {d1['donnees_audit'][:100] if d1['donnees_audit'] else 'None'}")
    else:
        print("Lead 1592 not found in leads_bruts!")
        
    print("\n=== INSPECTING LEAD 1592 IN LEADS_AUDITES ===")
    cur2 = conn.execute("SELECT * FROM leads_audites WHERE lead_id = 1592")
    row2 = cur2.fetchone()
    if row2:
        d2 = dict(row2)
        print(f"Lead ID: {d2['lead_id']} | Objet: {d2['email_objet']} | Template: {d2['template_used']}")
        print(f"Email corps: {d2['email_corps'][:100] if d2['email_corps'] else 'None'}")
    else:
        print("Lead 1592 not found in leads_audites!")

if __name__ == '__main__':
    main()
