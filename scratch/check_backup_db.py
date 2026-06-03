import sqlite3
import os

db = r'd:\prospection-machine\backups\pre-refact-2026-04-16\database\prospection.db'
size = os.path.getsize(db)
conn = sqlite3.connect(db)
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print(f'Taille: {size/1024/1024:.2f} MB')
for t in tables:
    c = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
    print(f'  {t}: {c} rows')

# Si leads_bruts existe, afficher un apercu
if 'leads_bruts' in tables:
    print("\n--- Apercu leads_bruts (5 premiers) ---")
    rows = conn.execute("SELECT id, nom, ville, secteur, statut FROM leads_bruts LIMIT 5").fetchall()
    for r in rows:
        print(r)
    
    print("\n--- Distribution par statut ---")
    rows = conn.execute("SELECT statut, COUNT(*) FROM leads_bruts GROUP BY statut").fetchall()
    for r in rows:
        print(r)

conn.close()
