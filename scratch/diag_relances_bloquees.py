"""Explique les 60 relances échues : matching (campagne, liste, position, count)
contre relance_batches — le garde-fou « lot inchangé » bloque-t-il l'envoi ?"""
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

    # ── relances dues (même règle que relances_due) ─────────────────────────
    today = datetime.utcnow().date()
    due_by_batch = defaultdict(list)
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
        due = add_business_days(last, int(t['delai_jours'] or 0))
        if due.date() <= today:
            due_by_batch[(m['campagne_id'], m['liste_id'], pos)].append(
                {'pid': pid, 'due': due, 'm': m})

    # ── état des lots existants ─────────────────────────────────────────────
    batches = {r['callback_id']: dict(r) for r in
               rows(conn, 'SELECT * FROM relance_batches')}

    print('=' * 100)
    print('RELANCES DUES — comparaison avec le lot existant (clé v2_batch_<camp>_<liste>)')
    print('Garde-fou : si lot statut=sent/erreur/refuse ET position ET count inchangés')
    print('            => AUCUNE nouvelle demande Telegram => relance bloquée à vie.')
    print('=' * 100)
    hdr = (f'{"camp":>4} {"liste":>6} {"pos":>4} {"dues":>5} | {"lot statut":10} '
           f'{"lot pos":>7} {"lot cnt":>7} | verdict')
    print(hdr)
    print('-' * 100)

    bloquee_garde = []
    sans_lot = []
    autre = []
    for (cid, lid, pos), cands in sorted(due_by_batch.items(),
                                         key=lambda kv: -len(kv[1])):
        cb = f'v2_batch_{cid}_{lid}'
        b = batches.get(cb)
        n = len(cands)
        if not b:
            verdict = '❌ AUCUN LOT → jamais demandé'
            sans_lot.append((cid, lid, pos, n, cands))
            print(f'{cid:>4} {lid:>6} {pos:>4} {n:>5} | {"(absent)":10} {"-":>7} {"-":>7} | {verdict}')
        elif b['statut'] in ('refuse', 'sent', 'erreur') \
                and int(b['position']) == pos and int(b['count']) == n:
            verdict = (f'🔒 GARDE-FOU « lot inchangé » → '
                       f'plus jamais redemandé (lot={b["statut"]})')
            bloquee_garde.append((cid, lid, pos, n, b, cands))
            print(f'{cid:>4} {lid:>6} {pos:>4} {n:>5} | {b["statut"]:10} '
                  f'{b["position"]:>7} {b["count"]:>7} | {verdict}')
        else:
            statut = b['statut'] if b else '(absent)'
            raison = ('position différente' if b and int(b['position']) != pos
                      else 'count différent' if b and int(b['count']) != n
                      else 'statut non bloquant')
            verdict = f'⏳ devrait redemander ({raison}) → job soit pas lancé'
            autre.append((cid, lid, pos, n, b, cands))
            print(f'{cid:>4} {lid:>6} {pos:>4} {n:>5} | {statut:10} '
                  f'{b["position"] if b else "-":>7} {b["count"] if b else "-":>7} | {verdict}')

    print('-' * 100)
    tot = sum(len(v) for v in due_by_batch.values())
    print(f'TOTAL dues={tot}  |  bloquées par garde-fou={sum(x[3] for x in bloquee_garde)}'
          f'  |  sans aucun lot={sum(x[3] for x in sans_lot)}'
          f'  |  devraient être demandées={sum(x[3] for x in autre)}')

    # ── détail des lots bloquants ───────────────────────────────────────────
    if bloquee_garde:
        print()
        print('=' * 100)
        print('DÉTAIL — lots « sent » qui retiennent des relances jamais parties')
        print('=' * 100)
        for cid, lid, pos, n, b, cands in bloquee_garde:
            nom = cands[0]['m']['liste_nom']
            print(f'  lot {b["callback_id"]}  statut={b["statut"]} '
                  f'position={b["position"]} count={b["count"]} '
                  f' créé={b["created_at"]} dernier MAJ={b["updated_at"]} '
                  f'tentatives={b["tentatives"]}')
            print(f'     liste « {nom} » (#{lid}) — {n} relances dues à ce jour, '
                  f'position {pos} = IDENTIQUE → bloquées')
            dues = sorted(cands, key=lambda c: c['due'])[:5]
            for c in dues:
                print(f'        prospect {c["pid"]:>6} échue depuis {c["due"]:%Y-%m-%d} '
                      f'({(today - c["due"].date()).days}j) statut={c["m"]["statut"]}')

    # ── vérif : le lot a-t-il réellement tout envoyé ? ──────────────────────
    print()
    print('=' * 100)
    print('CONTRÔLE : ces lots « sent » ont-ils VRAIMENT envoyé ? '
          '(événements de touche par liste)')
    print('=' * 100)
    for cb, b in sorted(batches.items()):
        cid, lid = int(b['campagne_id']), int(b['liste_id'])
        n_ev = conn.execute(f"""
            SELECT COUNT(DISTINCT ev.prospect_id)
            FROM prospect_events ev
            JOIN prospects p ON p.id = ev.prospect_id
            WHERE p.liste_id = ? AND ev.event_type = ?
              AND ev.created_at >= ?""", (lid, f'relance_{b["position"]}',
                                          b['updated_at'][:10] if b['updated_at'] else '1970-01-01')
                            ).fetchone()[0]
        print(f'  {cb:22} statut={b["statut"]:7} count_déclaré={b["count"]:>4} '
              f'→ prospects avec événement relance_{b["position"]} '
              f'depuis {b["updated_at"][:10] if b["updated_at"] else "?"} : {n_ev}')

    conn.close()


if __name__ == '__main__':
    main()
