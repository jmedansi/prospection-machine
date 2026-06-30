import sqlite3
import json

DB = 'data/prospection.db'
LIST_ID = 2

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
c = conn.cursor()

c.execute('''
SELECT lb.lead_id AS id, l.nom, l.site_web, l.email, l.email_2, l.email_valide, l.nom_gerant, l.prenom_gerant
FROM lead_list_items lb
JOIN leads_bruts l ON lb.lead_id = l.id
WHERE lb.list_id = ?
LIMIT 20
''', (LIST_ID,))
rows = [dict(r) for r in c.fetchall()]
print(json.dumps(rows, ensure_ascii=False, indent=2))
conn.close()
