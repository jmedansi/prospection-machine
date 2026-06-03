# -*- coding: utf-8 -*-
import sqlite3
import os

def main():
    db_path = 'data/prospection.db'
    if not os.path.exists(db_path):
        # Fallback to local
        db_path = '../data/prospection.db'
        
    print(f"Connecting to database: {os.path.abspath(db_path)}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    cur = conn.execute(
        "SELECT COUNT(*) FROM leads_bruts WHERE statut='en_attente' AND (source LIKE '%ads%' OR source LIKE '%google%')"
    )
    count = cur.fetchone()[0]
    print(f"Total pending ads leads: {count}")
    
    # Let's list the top 2
    cur2 = conn.execute(
        "SELECT * FROM leads_bruts WHERE statut='en_attente' AND (source LIKE '%ads%' OR source LIKE '%google%') ORDER BY id DESC LIMIT 2"
    )
    rows = cur2.fetchall()
    print("\nFull details of top 2 pending leads:")
    import json
    for r in rows:
        d = dict(r)
        # truncate large fields if any
        if d.get('donnees_audit'):
            try:
                d['donnees_audit'] = json.loads(d['donnees_audit'])
            except:
                pass
        print(json.dumps(d, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
