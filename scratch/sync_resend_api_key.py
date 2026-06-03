# -*- coding: utf-8 -*-
import sqlite3
import os

def main():
    db_path = 'data/prospection.db'
    if not os.path.exists(db_path):
        db_path = '../data/prospection.db'
        
    env_path = '.env'
    if not os.path.exists(env_path):
        env_path = '../.env'
        
    if not os.path.exists(env_path):
        print("Error: .env file not found.")
        return
        
    # 1. Parse .env for RESEND_API_KEY and sender details
    resend_key = None
    sender_email = None
    sender_name = None
    
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line_strip = line.strip()
            if not line_strip or line_strip.startswith('#'):
                continue
            if '=' in line_strip:
                parts = line_strip.split('=', 1)
                k = parts[0].strip()
                v = parts[1].strip()
                if k == 'RESEND_API_KEY':
                    resend_key = v
                elif k == 'BREVO_SENDER_EMAIL' or k == 'SENDER_EMAIL':
                    sender_email = v
                elif k == 'BREVO_SENDER_NAME' or k == 'SENDER_NAME':
                    sender_name = v
                    
    print("=== EXTRACTED FROM .ENV ===")
    print(f"RESEND_API_KEY: {resend_key[:15] if resend_key else 'None'}...")
    print(f"Sender Email:   {sender_email}")
    print(f"Sender Name:    {sender_name}")
    
    if not resend_key:
        print("Error: RESEND_API_KEY not found in .env.")
        return
        
    # 2. Update resend_accounts table in SQLite
    conn = sqlite3.connect(db_path)
    cur = conn.execute("SELECT COUNT(*) FROM resend_accounts WHERE id = 1")
    exists = cur.fetchone()[0] > 0
    
    # Defaults if not in env
    if not sender_email:
        sender_email = 'jmedansi@incidenx.com'
    if not sender_name:
        sender_name = 'Jean-Marc DANSI'
        
    if exists:
        conn.execute("""
            UPDATE resend_accounts
            SET api_key = ?, sender_email = ?, sender_name = ?, actif = 1
            WHERE id = 1
        """, (resend_key, sender_email, sender_name))
        print("\n[SUCCESS] Updated resend_accounts (ID 1) with real credentials!")
    else:
        conn.execute("""
            INSERT INTO resend_accounts (id, api_key, sender_email, sender_name, daily_usage, last_reset, actif)
            VALUES (1, ?, ?, ?, 0, date('now'), 1)
        """, (resend_key, sender_email, sender_name))
        print("\n[SUCCESS] Created and populated resend_accounts (ID 1) with real credentials!")
        
    conn.commit()
    
    # Verify DB update
    cur_v = conn.execute("SELECT * FROM resend_accounts WHERE id = 1")
    r = cur_v.fetchone()
    print("\n=== VERIFYING DB VALUES ===")
    print(f"ID:           {r[0]}")
    print(f"API Key:      {r[1][:15]}...")
    print(f"Sender Email: {r[2]}")
    print(f"Sender Name:  {r[3]}")
    print(f"Actif:        {r[6]}")

if __name__ == '__main__':
    main()
