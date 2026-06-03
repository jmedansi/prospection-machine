import sqlite3

conn = sqlite3.connect('data/prospection.db')
conn.row_factory = sqlite3.Row

# 1. Annuler toutes les campagnes Maps planifiées futures
cur = conn.execute("UPDATE planned_campaigns SET statut='cancelled' WHERE source='maps' AND statut='planned' AND date_planifiee >= date('now')")
print(f'[1] Campagnes Maps planifiees annulees: {cur.rowcount}')

# 2. S'assurer que maps_auto_scrape est bien a 0 en DB
conn.execute("INSERT OR REPLACE INTO planning_settings (key, value) VALUES ('maps_auto_scrape', '0')")
print('[2] maps_auto_scrape force a 0 en DB')

conn.commit()
conn.close()
print('[OK] Termine.')
