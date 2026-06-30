import sqlite3
from pathlib import Path

path = Path('data/prospection.db')
conn = sqlite3.connect(path)
cur = conn.cursor()
print('DB exists:', path.exists())
print('Tables:')
for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table'"):
    print(' -', row[0])
print('\nSchema of leads_bruts:')
for row in cur.execute("PRAGMA table_info(leads_bruts)"):
    print(row)
print('\nSample row:')
row = cur.execute('SELECT * FROM leads_bruts LIMIT 1').fetchone()
print(row)
conn.close()
