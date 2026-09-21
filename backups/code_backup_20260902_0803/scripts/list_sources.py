import sqlite3
from pathlib import Path
DB = Path(__file__).resolve().parents[1] / 'data' / 'prospection.db'
conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row
cur = conn.execute("SELECT DISTINCT source FROM leads_bruts ORDER BY source")
for row in cur.fetchall():
    print(row[0])
