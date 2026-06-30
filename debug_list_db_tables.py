import sqlite3
from pathlib import Path

candidates = [
    Path('database/prospection.db'),
    Path('database/db.sqlite'),
    Path('database/leads.db'),
    Path('database/database.db'),
    Path('data/prospection.db'),
    Path('database.db'),
]
for db in candidates:
    print('DB:', db, 'exists:', db.exists())
    if not db.exists():
        continue
    try:
        conn = sqlite3.connect(db)
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cur.fetchall()]
        print(' tables:', tables)
        conn.close()
    except Exception as e:
        print(' error:', type(e).__name__, e)
    print('---')
