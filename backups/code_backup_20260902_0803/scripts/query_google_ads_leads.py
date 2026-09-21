import sqlite3, json, sys
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / 'data' / 'prospection.db'
conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row
cur = conn.execute("SELECT id, nom, source, campaign_id, statut, site_web, email FROM leads_bruts WHERE statut='en_attente' AND source IS NOT NULL AND lower(source) LIKE '%google%' LIMIT 10")
rows = cur.fetchall()
print(json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2))
