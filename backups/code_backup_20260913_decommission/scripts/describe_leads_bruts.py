import sqlite3, json
conn = sqlite3.connect('data/prospection.db')
c = conn.cursor()
c.execute("PRAGMA table_info('leads_bruts')")
cols = c.fetchall()
print(json.dumps(cols, ensure_ascii=False, indent=2))
conn.close()
