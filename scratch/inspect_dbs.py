# -*- coding: utf-8 -*-
import os
import sqlite3
from pathlib import Path

def inspect_db(db_path):
    print(f"\nInspecting DB: {db_path}")
    if not os.path.exists(db_path):
        print("  File does not exist.")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [t[0] for t in cursor.fetchall()]
        print(f"  Tables found: {', '.join(tables)}")
        
        if 'leads_bruts' in tables:
            cursor.execute("SELECT COUNT(*) FROM leads_bruts")
            count = cursor.fetchone()[0]
            print(f"  leads_bruts row count: {count}")
            
            cursor.execute("SELECT source, COUNT(*) FROM leads_bruts GROUP BY source")
            sources = cursor.fetchall()
            print(f"  Sources: {sources}")
            
            cursor.execute("SELECT secteur, COUNT(*) FROM leads_bruts GROUP BY secteur")
            secteurs = cursor.fetchall()
            print(f"  Secteurs: {secteurs}")
            
            cursor.execute("SELECT MAX(date_scraping) FROM leads_bruts")
            max_date = cursor.fetchone()[0]
            print(f"  Max date_scraping: {max_date}")
        else:
            print("  Table leads_bruts NOT found.")
            
        if 'leads_audites' in tables:
            cursor.execute("SELECT COUNT(*) FROM leads_audites")
            count_audited = cursor.fetchone()[0]
            print(f"  leads_audites row count: {count_audited}")
            
        conn.close()
    except Exception as e:
        print(f"  Error reading DB: {e}")

def main():
    db_paths = [
        "data/prospection.db",
        "data/database.sqlite",
        "database.db",
        "prospection.db",
        "database/database.db",
        "database/db.sqlite",
        "database/leads.db",
        "database/prospection.db"
    ]
    
    for path in db_paths:
        inspect_db(path)

if __name__ == "__main__":
    main()
