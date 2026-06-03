# -*- coding: utf-8 -*-
import sqlite3
import os

def main():
    db_path = 'data/prospection.db'
    if not os.path.exists(db_path):
        db_path = '../data/prospection.db'
        
    conn = sqlite3.connect(db_path)
    
    # Update quota in database
    conn.execute("""
        INSERT INTO planning_settings (key, value) VALUES ('sniper_daily_quota', '50')
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
    """)
    conn.commit()
    
    # Verify the update
    cur = conn.execute("SELECT value FROM planning_settings WHERE key='sniper_daily_quota'")
    row = cur.fetchone()
    print(f"[SUCCESS] Updated daily quota 'sniper_daily_quota' to: {row[0]}")

if __name__ == '__main__':
    main()
