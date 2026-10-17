"""Pourquoi 390 copies doublonnées en base mais seulement 29 réellement envoyables ?"""
import sqlite3, sys
from collections import Counter
sys.stdout.reconfigure(encoding='utf-8')

DB = 'file:D:/prospection-machine/data/prospection.db?mode=ro'

conn = sqlite3.connect(DB, uri=True)
conn.row_factory = sqlite3.Row

# Tous les prospects faisant partie d'un groupe d'email dupliqué dans la même liste
dup_ids = [r['id'] for r in conn.execute('''
    SELECT p.id FROM prospects p
    JOIN (SELECT liste_id, LOWER(TRIM(email)) AS e, COUNT(*) AS c
          FROM prospects
          WHERE email IS NOT NULL AND TRIM(email) != ''
          GROUP BY liste_id, LOWER(TRIM(email)) HAVING COUNT(*) > 1) d
      ON d.liste_id = p.liste_id AND LOWER(TRIM(p.email)) = d.e
''')]
print(f'Prospects appartenant à un groupe dupliqué (même liste) : {len(dup_ids)}')

ph = ','.join('?' * len(dup_ids))
rows = conn.execute(f'''
    SELECT p.*, (p.email IS NULL OR TRIM(p.email)='') AS sans_email,
           (p.statut != 'qualifie') AS pas_qualifie,
           (p.ecarte = 1) AS ecarte,
           (p.ne_plus_contacter = 1) AS oppose,
           (LOWER(TRIM(p.email)) IN (SELECT LOWER(email) FROM suppression_list)) AS supprime
    FROM prospects p WHERE p.id IN ({ph})
''', dup_ids)

buckets = Counter()
still = 0
for r in rows:
    if r['sans_email']:
        buckets['sans email'] += 1
    elif r['pas_qualifie']:
        buckets[f'statut != qualifie ({r["statut"]})'] += 1
    elif r['ecarte']:
        buckets['écarté'] += 1
    elif r['oppose']:
        buckets['désinscrit (opposition)'] += 1
    elif r['supprime']:
        buckets['liste de suppression (bounce)'] += 1
    else:
        buckets['ÉLIGIBLE à l\'envoi'] += 1
        still += 1

print()
print('Répartition des critères de blocage :')
for k, v in buckets.most_common():
    print(f'  {k:44} {v:>5}')
print(f'\n  => {still} de ces prospects passent tous les verrous (statut=qualifie, '
      f'non écarté, non opposé, email valide, hors liste noire).')

# Combien de copies en trop parmi ces éligibles ?
print()
elig = [r['id'] for r in conn.execute(f'''
    SELECT p.id FROM prospects p
    WHERE p.id IN ({ph}) AND p.statut='qualifie' AND p.ecarte=0 AND p.ne_plus_contacter=0
      AND p.email IS NOT NULL AND TRIM(p.email) != ''
      AND LOWER(TRIM(p.email)) NOT IN (SELECT LOWER(email) FROM suppression_list)
''', dup_ids)]
cnt = Counter((r['liste_id'], r['email'].strip().lower())
              for r in conn.execute(f'SELECT liste_id, email FROM prospects WHERE id IN ({",".join("?"*len(elig))})', elig))
print(f'Copies éligibles dans une même liste : {len(elig)} pour {len(cnt)} couple(s) liste+adresse')
print(f'Envais initiaux redondants évitables  : {len(elig) - len(cnt)}')

conn.close()
