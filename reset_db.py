# -*- coding: utf-8 -*-
import sqlite3
import os
from pathlib import Path

DB_PATH = Path("d:/prospection-machine/data/prospection.db")

def truncate_all():
    if not DB_PATH.exists():
        print(f"Base de données introuvable : {DB_PATH}")
        return

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    tables = [
        'campagnes',
        'leads_bruts',
        'leads_audites',
        'emails_envoyes',
        'sync_log'
    ]

    print("--- VIDAGE COMPLET DE LA BASE DE DONNÉES (RESET TOTAL) ---")

    try:
        cursor.execute("PRAGMA foreign_keys=OFF")

        for table in tables:
            # Vérifier si la table existe
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
            if not cursor.fetchone():
                print(f"Table '{table}' absente, ignorée.")
                continue

            # Supprimer tout
            cursor.execute(f"DELETE FROM {table}")
            # Reset des autoincrements
            cursor.execute(f"DELETE FROM sqlite_sequence WHERE name='{table}'")
            print(f"✅ Table '{table}' : VIDÉE.")

        cursor.execute("PRAGMA foreign_keys=ON")
        conn.commit()
        print("--- Vidage SQLite terminé ---")

    except Exception as e:
        print(f"❌ Erreur lors du vidage : {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    truncate_all()
