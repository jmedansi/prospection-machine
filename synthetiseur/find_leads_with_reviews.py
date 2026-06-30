import sqlite3
from pathlib import Path

DB = Path(__file__).parent.parent / 'data' / 'prospection.db'

if __name__ == '__main__':
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('SELECT id, nom, rating, nb_avis, category, secteur, site_web FROM leads_bruts WHERE nb_avis IS NOT NULL AND nb_avis != "" ORDER BY id LIMIT 20')
    rows = cur.fetchall()
    for row in rows:
        print(dict(row))
    if not rows:
        print('No leads with nb_avis')
    conn.close()
