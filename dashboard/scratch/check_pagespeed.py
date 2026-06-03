
import sqlite3
import os
import json

db_path = "data/prospection.db"

def check_pagespeed_data():
    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    print("--- PAGESPEED DATA IN LEADS_BRUTS (last 20) ---")
    rows = conn.execute("SELECT id, nom, source, site_web, donnees_audit FROM leads_bruts WHERE source IN ('ads', 'tech', 'jobs', 'bodacc') ORDER BY id DESC LIMIT 20").fetchall()
    
    for row in rows:
        donnees = {}
        if row['donnees_audit']:
            try:
                donnees = json.loads(row['donnees_audit'])
            except:
                pass
        
        score = donnees.get('score_mobile') or donnees.get('mobile_score')
        reason = donnees.get('reason') or "N/A"
        
        print(f"ID: {row['id']} | Src: {row['source']} | Site: {row['site_web']} | Score: {score} | Reason: {reason[:50]}")

    conn.close()

if __name__ == "__main__":
    check_pagespeed_data()
