import sqlite3
import sys
import json
pattern = sys.argv[1] if len(sys.argv)>1 else 'debouchagedu66'
conn = sqlite3.connect('data/prospection.db')
cur = conn.cursor()
# Table current name is `leads_bruts` in this schema
q = "SELECT id,nom,site_web,email,source,statut FROM leads_bruts WHERE site_web LIKE ? OR nom LIKE ?"
like = f"%{pattern}%"
cur.execute(q, (like, like))
rows = cur.fetchall()
print(json.dumps(rows, ensure_ascii=False))
conn.close()
