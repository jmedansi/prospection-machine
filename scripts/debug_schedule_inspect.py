import sqlite3

conn = sqlite3.connect('data/prospection.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()
for lid in [19, 20, 21]:
    rows = cur.execute(
        'SELECT lb.id, lb.email, lb.email_valide, la.approuve, la.email_objet, la.email_corps '
        'FROM leads_bruts lb '
        'LEFT JOIN leads_audites la ON la.lead_id=lb.id '
        'JOIN lead_list_items lli ON lb.id=lli.lead_id '
        'WHERE lli.list_id=? ORDER BY lb.id',
        (lid,),
    ).fetchall()
    print('LIST', lid, 'count', len(rows))
    if rows:
        for r in rows[:5]:
            print(dict(r))
    print('---')
conn.close()
