import sqlite3, json
conn = sqlite3.connect('data/prospection.db')
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT id, nom, description, couleur, icone, (SELECT COUNT(*) FROM lead_list_items lli WHERE lli.list_id=lead_lists.id) as nb_leads FROM lead_lists ORDER BY updated_at DESC").fetchall()
print(json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2))
conn.close()
