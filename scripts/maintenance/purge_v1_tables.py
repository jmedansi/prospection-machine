# -*- coding: utf-8 -*-
"""
scripts/maintenance/purge_v1_tables.py
Purge définitive des tables V1 dans la base SQLite active.
"""
import os
import sys
import shutil
import sqlite3
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

from database.connection import DB_PATH

def purge_v1():
    print(f"Base de données cible : {DB_PATH}")
    
    # 1. Backup de précaution
    backup_dir = os.path.join(ROOT, "data", "backups")
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"prospection_pre_purge_{timestamp}.db")
    shutil.copy2(DB_PATH, backup_path)
    print(f"✓ Sauvegarde créée : {backup_path}")

    # 2. Suppression des tables V1
    tables_to_drop = [
        "leads_bruts",
        "leads_audites",
        "campagnes_legacy",
        "email_sequences",
        "planned_campaigns",
        "lead_lists",
        "lead_list_items",
    ]

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for table in tables_to_drop:
        try:
            cursor.execute(f"DROP TABLE IF EXISTS [{table}]")
            print(f"  ✓ Table supprimée : {table}")
        except Exception as e:
            print(f"  ⚠️ Erreur suppression {table} : {e}")

    conn.commit()

    # 3. VACUUM
    print("Exécution de VACUUM...")
    cursor.execute("VACUUM")
    conn.commit()

    # 4. État des tables restantes
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    tables = [row[0] for row in cursor.fetchall()]
    print("\nTables actives restantes en base V2 :")
    for t in tables:
        cursor.execute(f"SELECT COUNT(*) FROM [{t}]")
        cnt = cursor.fetchone()[0]
        print(f"  • {t:22s} : {cnt:6d} enregistrements")

    conn.close()
    print("\nPurge V1 terminée avec succès.")

if __name__ == "__main__":
    purge_v1()
