import sqlite3
db_path = r'd:\prospection-machine\data\prospection.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT id, nom, phase, source, started_at FROM campagnes WHERE phase IN ('scraping', 'enrichment', 'audit', 'email_gen')").fetchall()
for r in rows:
    print(f"ID: {r['id']}, Nom: {r['nom']}, Phase: {r['phase']}, Source: {r['source']}, Started: {r['started_at']}")
conn.close()
