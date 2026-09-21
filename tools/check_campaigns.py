import sqlite3

db = r'D:\prospection-machine\data\prospection.db'
conn = sqlite3.connect(db)
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print('TABLES:', tables)

candidates = [t for t in tables if any(k in t.lower() for k in ('campag', 'campagne', 'campaign', 'liste', 'listes'))]
print('POTENTIAL CAMPAIGN TABLES:', candidates)

if 'campagnes' in tables:
    try:
        cur.execute('SELECT * FROM campagnes')
        rows = cur.fetchall()
        print('campagnes rows:', len(rows))
        for r in rows[:20]:
            print(r)
    except Exception as e:
        print('error reading campagnes:', e)

# Search all tables for entries mentioning 'agence' to find lists
for t in tables:
    try:
        cur.execute(f"SELECT * FROM {t} WHERE nom LIKE '%agence%' OR nom LIKE '%agences%' OR nom LIKE '%web%' OR nom LIKE '%digital%'")
        rows = cur.fetchall()
        if rows:
            print(f'Matches in {t}:', len(rows))
            for r in rows[:5]:
                print(r)
    except Exception:
        pass

conn.close()

print('Done')

# Also print schema for key tables
import sqlite3 as _sqlite
conn2 = _sqlite.connect(db)
cur2 = conn2.cursor()
for t in ('campagnes', 'lead_lists', 'lead_list_items', 'listes'):
    try:
        cur2.execute(f"PRAGMA table_info({t})")
        cols = cur2.fetchall()
        print('\nSCHEMA', t, cols)
    except Exception:
        pass
conn2.close()
