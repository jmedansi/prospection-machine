import sqlite3
conn = sqlite3.connect('d:/prospection-machine/data/prospection.db')
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT id, lead_id, score_performance, audit_error FROM leads_audites WHERE lead_id=1948").fetchall()
print([dict(r) for r in rows])
