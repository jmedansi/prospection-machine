import sqlite3

conn = sqlite3.connect('d:/prospection-machine/data/prospection.db')
conn.row_factory = sqlite3.Row
schema = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='leads_audites'").fetchone()['sql']
print("SCHEMA:", schema)

# Count duplicates
dups = conn.execute("""
    SELECT lead_id, COUNT(*) as c
    FROM leads_audites
    GROUP BY lead_id
    HAVING c > 1
""").fetchall()
print(f"Total leads with duplicates: {len(dups)}")
