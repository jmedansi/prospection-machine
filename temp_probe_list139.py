import sqlite3
from pathlib import Path

DB = Path(r'D:\prospection-machine\data\prospection.db')
conn = sqlite3.connect(DB)
cur = conn.cursor()
print('LISTS:')
for row in cur.execute("SELECT * FROM listes WHERE id >= 130 AND id <= 150 ORDER BY id"):
    print(row)
print('\nLEAD_LIST_ITEMS SAMPLE:')
for row in cur.execute('SELECT * FROM lead_list_items LIMIT 10'):
    print(row)
print('\nITEMS FOR LIST 139:')
for row in cur.execute('SELECT * FROM lead_list_items WHERE list_id = 139 ORDER BY id LIMIT 20'):
    print(row)
print('\nLEADS FOR LIST 139:')
for row in cur.execute('SELECT id, nom, ville, site_web, telephone, email FROM leads_bruts WHERE id IN (SELECT lead_id FROM lead_list_items WHERE list_id = 139) ORDER BY id LIMIT 20'):
    print(row)
conn.close()
