
import sqlite3
import os

db_path = r'd:\prospection-machine\data\prospection.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.execute("SELECT lead_id, audit_error, mobile_score FROM leads_audites WHERE audit_error IS NOT NULL OR mobile_score = 0 LIMIT 10")
rows = cursor.fetchall()
for row in rows:
    print(dict(row))
conn.close()
