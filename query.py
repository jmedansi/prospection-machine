import sqlite3
conn = sqlite3.connect('d:/prospection-machine/data/prospection.db')
conn.row_factory = sqlite3.Row
row = conn.execute("SELECT la.* FROM leads_bruts lb LEFT JOIN leads_audites la ON la.lead_id = lb.id WHERE lb.nom LIKE '%supformation%'").fetchone()
print(dict(row) if row else 'Not found')
