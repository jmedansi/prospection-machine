import sqlite3, os
root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
db_path = os.path.join(root, 'data', 'prospection.db')
if not os.path.exists(db_path):
    print('DB_NOT_FOUND', db_path); raise SystemExit(2)
conn = sqlite3.connect(db_path)
cur = conn.cursor()
try:
    cur.execute("PRAGMA table_info('leads_audites')")
    rows = cur.fetchall()
    if not rows:
        print('NO_TABLE')
    else:
        for r in rows:
            cid, name, typ, notnull, dflt, pk = r
            print(f"{name}\t{typ}\tnotnull={notnull}\tdefault={dflt}\tpk={pk}")
finally:
    conn.close()
