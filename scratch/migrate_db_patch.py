# -*- coding: utf-8 -*-
import sqlite3
import os

def check_and_add_column(cursor, table, column, col_def):
    cursor.execute(f"PRAGMA table_info({table})")
    cols = {row[1] for row in cursor.fetchall()}
    if column not in cols:
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
            print(f"[OK] Added {table}.{column}")
        except Exception as e:
            print(f"[ERR] Failed to add {table}.{column}: {e}")
    else:
        print(f"[INFO] Column {table}.{column} already exists")

def main():
    db_path = 'data/prospection.db'
    if not os.path.exists(db_path):
        print(f"Error: {db_path} does not exist!")
        return
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Missing columns on leads_audites
    leads_audites_migrations = [
        ("audit_partial", "INTEGER DEFAULT 0"),
        ("audit_error", "TEXT"),
        ("notified_at", "TEXT")
    ]
    
    print("Migrating leads_audites...")
    for col, col_def in leads_audites_migrations:
        check_and_add_column(cursor, "leads_audites", col, col_def)
        
    # Missing columns on emails_envoyes
    emails_envoyes_migrations = [
        ("date_premiere_ouverture", "TEXT"),
        ("date_derniere_ouverture", "TEXT"),
        ("nb_clics", "INTEGER DEFAULT 0"),
        ("date_dernier_clic", "TEXT"),
        ("ip_ouverture", "TEXT"),
        ("user_agent_ouverture", "TEXT"),
        ("date_relance_prevue", "TEXT"),
        ("relance_type", "TEXT"),
        ("lead_temperature", "TEXT"),
        ("derniere_interaction", "TEXT"),
        ("score_lead", "INTEGER DEFAULT 0")
    ]
    
    print("\nMigrating emails_envoyes...")
    for col, col_def in emails_envoyes_migrations:
        check_and_add_column(cursor, "emails_envoyes", col, col_def)
        
    conn.commit()
    conn.close()
    print("\nMigration completed successfully!")

if __name__ == "__main__":
    main()
