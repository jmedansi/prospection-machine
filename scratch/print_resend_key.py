# -*- coding: utf-8 -*-
import sqlite3
import os

def main():
    db_path = 'data/prospection.db'
    if not os.path.exists(db_path):
        db_path = '../data/prospection.db'
        
    conn = sqlite3.connect(db_path)
    cur = conn.execute("SELECT api_key FROM resend_accounts LIMIT 1")
    row = cur.fetchone()
    if row:
        print(f"Exact API key value in DB: '{row[0]}'")
    else:
        print("No resend accounts found.")

if __name__ == '__main__':
    main()
