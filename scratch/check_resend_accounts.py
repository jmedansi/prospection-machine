# -*- coding: utf-8 -*-
import sqlite3
import os

def main():
    db_path = 'data/prospection.db'
    if not os.path.exists(db_path):
        db_path = '../data/prospection.db'
        
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    print("=== INSPECTING RESEND ACCOUNTS ===")
    
    try:
        cur = conn.execute("SELECT * FROM resend_accounts")
        rows = cur.fetchall()
        print(f"Total resend accounts registered: {len(rows)}")
        
        for r in rows:
            print("\nRow details:")
            for k in r.keys():
                val = r[k]
                if k == 'api_key' and val:
                    val = val[:10] + "..."
                print(f"  {k}: {val}")
            
    except Exception as e:
        print(f"Error reading resend_accounts table: {e}")

if __name__ == '__main__':
    main()
