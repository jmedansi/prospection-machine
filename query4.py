import sqlite3
conn = sqlite3.connect('d:/prospection-machine/data/prospection.db')
conn.row_factory = sqlite3.Row
row = conn.execute("SELECT mobile_score, score_performance FROM leads_audites WHERE lead_id=1948").fetchone()
print(dict(row) if row else 'Not found')
