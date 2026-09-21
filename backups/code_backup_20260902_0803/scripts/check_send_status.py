import sqlite3

DB = 'data/prospection.db'
list_names = [
    'Cliniques Esthétiques — 25 leads non contactés (7/13)',
    'Cliniques Esthétiques — 25 leads non contactés (8/13)',
    'Cliniques Esthétiques — 25 leads non contactés (9/13)'
]

with sqlite3.connect(DB) as conn:
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    for name in list_names:
        lid_row = cur.execute('SELECT id FROM lead_lists WHERE nom=?', (name,)).fetchone()
        if not lid_row:
            print(f'MISSING list: {name}')
            continue
        lid = lid_row['id']
        lead_ids = [r['lead_id'] for r in cur.execute('SELECT lead_id FROM lead_list_items WHERE list_id=?', (lid,)).fetchall()]
        if not lead_ids:
            print(f'EMPTY list: {name}')
            continue
        placeholders = ','.join('?' for _ in lead_ids)
        scheduled = cur.execute(f'SELECT count(*) FROM emails_envoyes WHERE lead_id IN ({placeholders}) AND statut_envoi = "scheduled"', lead_ids).fetchone()[0]
        sent = cur.execute(f'SELECT count(*) FROM emails_envoyes WHERE lead_id IN ({placeholders}) AND statut_envoi = "envoye"', lead_ids).fetchone()[0]
        other = cur.execute(f'SELECT count(*) FROM emails_envoyes WHERE lead_id IN ({placeholders}) AND statut_envoi NOT IN ("scheduled","envoye")', lead_ids).fetchone()[0]
        print(f'{name}: total={len(lead_ids)}, scheduled={scheduled}, envoye={sent}, other={other}')
        rows = cur.execute(f'SELECT lead_id, statut_envoi, message_id_resend FROM emails_envoyes WHERE lead_id IN ({placeholders}) ORDER BY id DESC LIMIT 5', lead_ids).fetchall()
        for row in rows:
            print('  ', dict(row))
        print()