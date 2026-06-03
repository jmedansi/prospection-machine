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
    
    print("=== LIVE SENDING PROGRESS CHECK ===")
    
    # 1. Count emails sent today
    today_str = "2026-05-18"
    cur_today = conn.execute("""
        SELECT COUNT(*) as c 
        FROM emails_envoyes 
        WHERE date_envoi LIKE ?
    """, (f"{today_str}%",))
    sent_count = cur_today.fetchone()['c']
    print(f"Emails successfully sent today ({today_str}): {sent_count}")
    
    # 2. Show details of the most recent sends today
    if sent_count > 0:
        cur_recent = conn.execute("""
            SELECT id, email_destinataire, email_objet, date_envoi, statut_envoi
            FROM emails_envoyes
            WHERE date_envoi LIKE ?
            ORDER BY date_envoi DESC
            LIMIT 10
        """, (f"{today_str}%",))
        print("\n=== LAST 10 EMAILS DELIVERED JUST NOW ===")
        for idx, r in enumerate(cur_recent.fetchall(), 1):
            obj = r['email_objet'] or 'No Subject'
            print(f"{idx}. Dest: {r['email_destinataire']:<30} | Objet: {obj[:40]} | Date: {r['date_envoi']}")
            
    # 3. Check remaining ready-to-send leads in queue
    cur_queue = conn.execute("""
        SELECT COUNT(*) as c
        FROM leads_audites la
        JOIN leads_bruts lb ON lb.id = la.lead_id
        WHERE la.statut_prospection = 'a_contacter'
          AND la.approuve = 1
          AND la.email_valide IS NOT NULL AND la.email_valide != ''
          AND la.email_corps IS NOT NULL AND la.email_corps != ''
          AND lb.source IN ('ads', 'fb_ads', 'ecom', 'tech', 'jobs', 'bodacc')
    """)
    queue_count = cur_queue.fetchone()['c']
    print(f"\nRemaining leads ready in queue: {queue_count}")

if __name__ == '__main__':
    main()
