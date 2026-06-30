import sqlite3
conn = sqlite3.connect('data/prospection.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("""SELECT id, nom, secteur, category, ville FROM leads_bruts 
WHERE (site_web IS NULL OR site_web = '')
ORDER BY id ASC LIMIT 30""")
rows = cur.fetchall()
for r in rows:
    s = r['secteur'] or r['category'] or ''
    print(f"{r['id']}  {(r['nom'] or '')}  |  {s}  |  {(r['ville'] or '')}")
conn.close()
