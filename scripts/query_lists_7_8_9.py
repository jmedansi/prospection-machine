import sqlite3

DB = 'data/prospection.db'
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()
for lid in [7, 8, 9]:
    row = cur.execute('SELECT id, nom, description, couleur, icone FROM lead_lists WHERE id=?', (lid,)).fetchone()
    print('\nLIST', lid, row['nom'] if row else None)
    if row:
        rows = cur.execute(
            'SELECT lb.id, lb.nom, lb.site_web, lb.email_valide, lb.email, lb.secteur, lb.telephone FROM leads_bruts lb '
            'JOIN lead_list_items lli ON lb.id=lli.lead_id WHERE lli.list_id=? LIMIT 20',
            (lid,),
        ).fetchall()
        print('count', len(rows))
        for r in rows:
            print({k: r[k] for k in r.keys()})
conn.close()
