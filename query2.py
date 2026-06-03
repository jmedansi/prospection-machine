import sqlite3
conn = sqlite3.connect('d:/prospection-machine/data/prospection.db')
conn.row_factory = sqlite3.Row
row = conn.execute("SELECT id, statut, nom, site_web FROM leads_bruts WHERE nom LIKE '%supformation%'").fetchone()
print(dict(row) if row else 'Not found')
