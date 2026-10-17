"""Attribution exacte des relances dues : campagne + liste complets."""
import sqlite3, sys
from datetime import datetime, timedelta
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')
DB = 'file:D:/prospection-machine/data/prospection.db?mode=ro'
NEXT_POS = {'en_sequence': 1, 'relance_1': 2, 'relance_2': 3}


def add_business_days(start_dt, n_days):
    cur, added = start_dt, 0
    while added < n_days:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            added += 1
    return cur


def parse(s):
    try:
        return datetime.strptime(str(s)[:19], '%Y-%m-%d %H:%M:%S')
    except (TypeError, ValueError):
        return None


def rows(conn, sql, p=()):
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute(sql, p).fetchall()]


def main():
    conn = sqlite3.connect(DB, uri=True)
    conn.row_factory = sqlite3.Row

    steps = {}
    for r in conn.execute("SELECT * FROM sequence_templates WHERE actif=1 "
                          "ORDER BY COALESCE(campagne_id,999999), position, delai_jours"):
        d = dict(r)
        steps.setdefault((d['campagne_id'], d['position']), d)
    get_step = lambda c, p: steps.get((c, p)) or steps.get((None, p))

    ev_last = {r['prospect_id']: r['last'] for r in conn.execute("""
        SELECT prospect_id, MAX(created_at) AS last FROM prospect_events
        WHERE event_type IN ('initial','relance_1','relance_2','relance_3')
        GROUP BY prospect_id""")}

    meta = {r['id']: dict(r) for r in rows(conn, """
        SELECT p.id, p.statut, p.liste_id, l.nom AS liste_nom, l.type AS liste_type,
               l.campagne_id, c.nom AS campagne_nom, c.envoi_auto, c.validation_relances
        FROM prospects p JOIN listes l ON l.id=p.liste_id
        JOIN campagnes c ON c.id=l.campagne_id
        WHERE p.ecarte=0 AND p.ne_plus_contacter=0
          AND (l.type IS NULL OR l.type != 'corbeille')""")}

    today = datetime.utcnow().date()
    due = defaultdict(list)
    for pid, m in meta.items():
        if m['statut'] not in NEXT_POS:
            continue
        last = parse(ev_last.get(pid))
        if not last:
            continue
        pos = NEXT_POS[m['statut']]
        t = get_step(m['campagne_id'], pos)
        if not t:
            continue
        echeance = add_business_days(last, int(t['delai_jours'] or 0))
        if echeance.date() <= today:
            due[(m['campagne_id'], m['campagne_nom'], m['liste_id'],
                 m['liste_nom'], m['envoi_auto'], pos)].append(
                {'pid': pid, 'ech': echeance, 'statut': m['statut']})

    print('=' * 104)
    print(f'RELANCES DUES AU {today:%Y-%m-%d} — VENTILATION CAMPAGNE / LISTE')
    print('=' * 104)
    print(f'{"camp":>4}  {"CAMPAGNE":44} {"lst":>5} {"LISTE":36} {"pos":>4} {"n":>4} '
          f'{"auto":>5} {"retard_max":>10}')
    print('-' * 104)
    tot_by_camp = defaultdict(lambda: {'n': 0, 'nom': '', 'auto': None})
    for (cid, cnom, lid, lnom, auto, pos), lst in sorted(
            due.items(), key=lambda kv: (kv[0][0], -len(kv[1]))):
        retard = max((today - x['ech'].date()).days for x in lst)
        print(f'{cid:>4}  {cnom[:44]:44} {lid:>5} {lnom[:36]:36} {pos:>4} {len(lst):>4} '
              f'{auto:>5} {retard:>9}j')
        tot_by_camp[cid]['n'] += len(lst)
        tot_by_camp[cid]['nom'] = cnom
        tot_by_camp[cid]['auto'] = auto
    print('-' * 104)
    total = sum(v['n'] for v in tot_by_camp.values())
    print(f'TOTAL : {total} relances dues\n')
    print('PAR CAMPAGNE :')
    for cid, v in sorted(tot_by_camp.items(), key=lambda kv: -kv[1]['n']):
        part = 100 * v['n'] / total if total else 0
        print(f'  #{cid} « {v["nom"]} » : {v["n"]} relances ({part:.0f}%)  '
              f'envoi_auto={v["auto"]}')

    # ── campagne « Partenariats » : liste complète des prospects ─────────────
    print()
    print('=' * 104)
    print('DÉTAIL — prospects en attente dans « Agences digitales - Partenariats » (#44)')
    print('=' * 104)
    cible = [x for k, lst in due.items() if k[0] == 44 for x in lst]
    cible.sort(key=lambda x: x['ech'])
    for x in cible[:20]:
        m = meta[x['pid']]
        print(f'  prospect {x["pid"]:>6} statut={x["statut"]:12} '
              f'relance_{NEXT_POS[x["statut"]]} échue depuis {x["ech"]:%Y-%m-%d} '
              f'({(today - x["ech"].date()).days}j)  liste « {m["liste_nom"]} »')
    if len(cible) > 20:
        print(f'  ... et {len(cible) - 20} autres')

    conn.close()


if __name__ == '__main__':
    main()
