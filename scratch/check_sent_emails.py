# -*- coding: utf-8 -*-
import sqlite3
import os
from datetime import datetime

def main():
    db_path = 'data/prospection.db'
    if not os.path.exists(db_path):
        db_path = '../data/prospection.db'
        
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    print("=== CHECKING SENT EMAILS LOGS ===")
    
    # 1. Get total number of rows in emails_envoyes
    cur_total = conn.execute("SELECT COUNT(*) as c FROM emails_envoyes")
    total = cur_total.fetchone()['c']
    print(f"Total emails ever sent in database: {total}")
    
    # 2. Get emails sent today (2026-05-18)
    today_str = "2026-05-18"
    cur_today = conn.execute("""
        SELECT COUNT(*) as c 
        FROM emails_envoyes 
        WHERE date_envoi LIKE ?
    """, (f"{today_str}%",))
    today_count = cur_today.fetchone()['c']
    print(f"Emails sent today ({today_str}): {today_count}")
    
    # 3. Check recent sends in emails_envoyes
    cur_recent = conn.execute("""
        SELECT id, lead_id, email_destinataire, email_objet, date_envoi, statut_envoi
        FROM emails_envoyes
        ORDER BY date_envoi DESC
        LIMIT 15
    """)
    recent_rows = cur_recent.fetchall()
    if recent_rows:
        print("\n=== MOST RECENT SENT EMAILS ===")
        for r in recent_rows:
            obj = r['email_objet'] or 'No Subject'
            print(f"ID: {r['id']} | Dest: {r['email_destinataire']} | Objet: {obj[:45]} | Date: {r['date_envoi']} | Statut: {r['statut_envoi']}")
    else:
        print("\nNo recent sent emails found in emails_envoyes.")

    # 4. Check if there are leads marked as 'envoye' or 'step1_envoye' in database
    cur_statut = conn.execute("""
        SELECT statut, COUNT(*) as c
        FROM leads_bruts
        WHERE statut IN ('envoye', 'step1_envoye', 'email_sent')
        GROUP BY statut
    """)
    statut_rows = cur_statut.fetchall()
    if statut_rows:
        print("\n=== LEADS WITH 'SENT' STATUS IN LEADS_BRUTS ===")
        for r in statut_rows:
            print(f"Statut: {r['statut']:<15} | Count: {r['c']}")

    cur_prospection = conn.execute("""
        SELECT statut_prospection, COUNT(*) as c
        FROM leads_audites
        WHERE statut_prospection IN ('envoye', 'step1_envoye', 'email_sent')
        GROUP BY statut_prospection
    """)
    prospection_rows = cur_prospection.fetchall()
    if prospection_rows:
        print("\n=== LEADS WITH 'SENT' STATUS IN LEADS_AUDITES ===")
        for r in prospection_rows:
            print(f"Statut Prospection: {r['statut_prospection']:<15} | Count: {r['c']}")

if __name__ == '__main__':
    main()
