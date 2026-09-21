import sqlite3
conn = sqlite3.connect('d:/prospection-machine/data/prospection.db')
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT lead_id, statut_prospection FROM leads_audites WHERE statut_prospection='audit_echoue'").fetchall()
print([dict(r) for r in rows])
