"""Simule candidates_for() : combien d'emails partiraient, et à combien d'adresses distinctes."""
import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')

DB = 'file:D:/prospection-machine/data/prospection.db?mode=ro'


def rows(conn, sql, p=()):
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute(sql, p).fetchall()]


CAND_SQL = """
SELECT p.id, p.email, p.liste_id, l.nom AS liste_nom, c.id AS campagne_id, c.nom AS campagne_nom
FROM prospects p
JOIN listes l ON p.liste_id = l.id
JOIN campagnes c ON c.id = l.campagne_id
WHERE p.statut = 'qualifie'
  AND p.ecarte = 0
  AND p.ne_plus_contacter = 0
  AND p.email IS NOT NULL AND p.email != ''
  AND lower(p.email) NOT IN (SELECT lower(email) FROM suppression_list)
"""


def main():
    conn = sqlite3.connect(DB, uri=True)
    cands = rows(conn, CAND_SQL)

    print('=' * 78)
    print("SIMULATION « ▶ ENVOYER » — prospects éligibles (statut = qualifie)")
    print('=' * 78)
    print(f'{"campagne":34} {"éligibles":>9} {"adresses":>9} {"doublons envoyés":>17}')
    print('-' * 78)

    total_elig = total_addr = total_waste = 0
    by_camp = {}
    for c in cands:
        by_camp.setdefault(c['campagne_id'], []).append(c)

    for cid, lst in sorted(by_camp.items(), key=lambda kv: -len(kv[1])):
        addrs = {}
        for c in lst:
            addrs.setdefault(c['email'].strip().lower(), 0)
            addrs[c['email'].strip().lower()] += 1
        waste = sum(v - 1 for v in addrs.values() if v > 1)
        nom = (lst[0]['campagne_nom'] or '?')[:34]
        total_elig += len(lst); total_addr += len(addrs); total_waste += waste
        flag = '  <-- RISQUE' if waste else ''
        print(f'{nom:34} {len(lst):>9} {len(addrs):>9} {waste:>17}{flag}')
    print('-' * 78)
    print(f'{"TOTAL":34} {total_elig:>9} {total_addr:>9} {total_waste:>17}')

    print()
    print('=' * 78)
    print("PIRES CAS — adresses qui recevraient le MÊME mail initial plusieurs fois")
    print('=' * 78)
    addrs = {}
    for c in cands:
        k = c['email'].strip().lower()
        addrs.setdefault(k, []).append(c)
    worst = sorted(((k, v) for k, v in addrs.items() if len(v) > 1),
                   key=lambda kv: -len(kv[1]))
    print(f'  {len(worst)} adresses seraient contactées en double.\n')
    for k, v in worst[:15]:
        c0 = v[0]
        print(f'  {k:40} x{len(v)}  campagne « {c0["campagne_nom"]} »')
    if len(worst) > 15:
        print(f'  ... et {len(worst)-15} autres')

    print()
    print('=' * 78)
    print('VENTILATION PAR LISTE (les 3 listes à problème)')
    print('=' * 78)
    for lid in (146, 144, 143):
        lst = [c for c in cands if c['liste_id'] == lid]
        if not lst:
            continue
        addrs2 = {}
        for c in lst:
            addrs2[c['email'].strip().lower()] = addrs2.get(c['email'].strip().lower(), 0) + 1
        w = sum(v - 1 for v in addrs2.values() if v > 1)
        print(f'  liste {lid} « {c0["liste_nom"] if False else ""}{lst[0]["liste_nom"][:30]:30} » : '
              f'{len(lst)} éligibles -> {len(addrs2)} adresses (=> {w} doublons évitables)')

    conn.close()


if __name__ == '__main__':
    main()
