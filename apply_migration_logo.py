# apply_migration_logo.py
# Applique la migration logo_url sur leads_bruts (colonne manquante)
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / 'data' / 'prospection.db'

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("PRAGMA table_info(leads_bruts)")
cols = [c[1] for c in cur.fetchall()]
print("Colonnes actuelles de leads_bruts:", cols)

if 'logo_url' not in cols:
    cur.execute("ALTER TABLE leads_bruts ADD COLUMN logo_url TEXT DEFAULT ''")
    conn.commit()
    print("[OK] Colonne logo_url ajoutée à leads_bruts")
else:
    print("[OK] Colonne logo_url déjà présente")

# Vérification
cur.execute("PRAGMA table_info(leads_bruts)")
cols = [c[1] for c in cur.fetchall()]
print("Colonnes après migration:", cols)
print("logo_url présent:", 'logo_url' in cols)

conn.close()
