# -*- coding: utf-8 -*-
import sqlite3
import os
from pathlib import Path

DB_PATH = Path("d:/prospection-machine/data/prospection.db")
TODAY = "2026-03-20"

def cleanup():
    if not DB_PATH.exists():
        print(f"Base de données introuvable : {DB_PATH}")
        return

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    tables_to_clean = {
        'campagnes': 'date_creation',
        'leads_bruts': 'date_scraping',
        'leads_audites': 'date_audit',
        'emails_envoyes': 'date_envoi',
        'sync_log': 'date_sync'
    }

    print(f"--- Nettoyage de la base de données (avant le {TODAY}) ---")

    try:
        # Désactiver temporairement les foreign keys pour éviter les blocages de suppression
        # (Bien que ON DELETE CASCADE soit présent, c'est plus sûr en cas de dates incohérentes)
        cursor.execute("PRAGMA foreign_keys=OFF")

        for table, date_col in tables_to_clean.items():
            # Vérifier si la table existe
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
            if not cursor.fetchone():
                print(f"Table '{table}' absente, ignorée.")
                continue

            # Compter avant
            cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE {date_col} < ?", (TODAY,))
            count = cursor.fetchone()[0]

            if count > 0:
                cursor.execute(f"DELETE FROM {table} WHERE {date_col} < ?", (TODAY,))
                print(f"✅ Table '{table}' : {count} entrées supprimées.")
            else:
                print(f"ℹ️ Table '{table}' : Aucune entrée ancienne trouvée.")

        # Réactiver les foreign keys
        cursor.execute("PRAGMA foreign_keys=ON")
        conn.commit()
        print("--- Nettoyage terminé ---")

    except Exception as e:
        print(f"❌ Erreur lors du nettoyage : {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    cleanup()
