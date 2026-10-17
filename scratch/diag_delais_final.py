"""Vérification finale — 1) jours OUVRÉS en dates pures (corrige l'off-by-one
de mon helper précédent)  2) cause exacte des relances échues."""
import sqlite3, sys
from datetime import datetime, timedelta, date
from collections import defaultdict, Counter

sys.stdout.reconfigure(encoding='utf-8')
DB = 'file:D:/prospection-machine/data/prospection.db?mode=ro'
TOUCHES = ('initial', 'relance_1', 'relance_2', 'relance_3')
NEXT_POS = {'en_sequence': 1, 'relance_1': 2, 'relance_2': 3}


def add_business_days(start_dt, n_days):
    """IDENTIQUE core.orchestration.add_business_days."""
    cur, added = start_dt, 0
    while added < n_days:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            added += 1
    return cur


def bdays_dates(a: date, b: date) -> int:
    """Jours ouvrés STRICTEMENT entre a (inclus après a) et b (inclus) — dates pures."""
    if b <= a:
        return 0
    n, cur = 0, a
    while cur < b:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            n += 1
    return n


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

    ev_by_p = defaultdict(list)
    for r in conn.execute(f"""SELECT ev.id, ev.prospect_id, ev.event_type, ev.created_at
                              FROM prospect_events ev
                              WHERE ev.event_type IN ({','.join('?'*len(TOUCHES))})
                              ORDER BY ev.prospect_id, ev.created_at, ev.id""", TOUCHES):
        ev_by_p[r['prospect_id']].append(dict(r))

    meta = {r['id']: dict(r) for r in rows(conn, """
        SELECT p.id, p.email, p.statut, p.liste_id, l.nom AS liste_nom, l.campagne_id,
               c.nom AS campagne_nom, c.max_touches, c.envoi_auto, c.validation_relances
        FROM prospects p JOIN listes l ON l.id=p.liste_id
        JOIN campagnes c ON c.id=l.campagne_id""")}

    # ═══ 1. DÉLAI OBSERVÉ — dates pures ═══════════════════════════════════════
    print('=' * 94)
    print('1. DÉLAI RÉEL OBSERVÉ (jours ouvrés, calcul en DATES PURES) vs config actuelle')
    print('   Règle de non-violation : échéance = dernière touche + delai_jours (ouvrés)')
    print('=' * 94)
    obs = defaultdict(list)
    viol = []
    for pid, evs in ev_by_p.items():
        m = meta.get(pid)
        if not m:
            continue
        for i, ev in enumerate(evs):
            if ev['event_type'] == 'initial' or i == 0:
                continue
            pos = int(ev['event_type'].split('_')[1])
            cur, prev = parse(ev['created_at']), parse(evs[i - 1]['created_at'])
            if not (cur and prev):
                continue
            t = get_step(m['campagne_id'], pos)
            cfg = int(t['delai_jours']) if t and t.get('delai_jours') is not None else 0
            due = add_business_days(prev, cfg)
            gap = bdays_dates(prev.date(), cur.date())
            obs[(m['campagne_id'], m['campagne_nom'], pos, cfg)].append(gap)
            if cur.date() < due.date():          # IDENTIQUE à delai_non_atteint()
                viol.append((m, ev, prev, due, cur, cfg, gap))

    print(f'{"campagne":38} {"pos":>4} {"cfg":>5} {"n":>4} {"min":>4} {"méd":>4} {"max":>4}  verdict')
    print('-' * 94)
    for (cid, cnom, pos, cfg), gaps in sorted(obs.items(), key=lambda kv: (kv[0][0], kv[0][2])):
        g = sorted(gaps)
        n_early = sum(1 for x in g if x < cfg)
        verdict = 'OK — 0 envoi avant échéance' if n_early == 0 \
            else f'❌ {n_early}/{len(g)} avant échéance (min={min(g)}j vs cfg={cfg}j)'
        print(f'{cnom[:38]:38} {pos:>4} {str(cfg)+"j":>5} {len(g):>4} '
              f'{min(g):>4} {g[len(g)//2]:>4} {max(g):>4}  {verdict}')

    print()
    print(f'❌ VIOLATIONS DU DÉLAI (échéance dépassée à la date d\'envoi) : {len(viol)}')
    for m, ev, prev, due, cur, cfg, gap in viol:
        manque = bdays_dates(cur.date(), due.date())
        print(f'   prospect {m["id"]:>6} {m["email"][:36]:36} {ev["event_type"]}')
        print(f'      touche précédente {prev:%Y-%m-%d %a} + {cfg}j ouvrés => {due:%Y-%m-%d %a}')
        print(f'      envoyé {cur:%Y-%m-%d %a}  => {manque} jour(s) ouvré(s) EN AVANCE')
    if not viol:
        print('   ✅ AUCUNE — toutes les relances envoyées respectent leur échéance.')

    # ═══ 2. RELANCES ÉCHUES — cause ═══════════════════════════════════════════
    print()
    print('=' * 94)
    print('2. RELANCES ÉCHUES (échéance passée, jamais envoyées) — ventilation par campagne')
    print('=' * 94)
    today = datetime.utcnow().date()
    overdue = []
    for pid, evs in ev_by_p.items():
        m = meta.get(pid)
        if not m or not evs or m['statut'] not in NEXT_POS:
            continue
        last = parse(evs[-1]['created_at'])
        if not last:
            continue
        pos = NEXT_POS[m['statut']]
        t = get_step(m['campagne_id'], pos)
        if not t:
            continue
        due = add_business_days(last, int(t['delai_jours'] or 0))
        if due.date() <= today:
            overdue.append({'m': m, 'pos': pos, 'due': due, 'last': last})

    agg = defaultdict(lambda: {'n': 0, 'max_retard': 0, 'auto': None, 'val': None, 'camp': ''})
    for o in overdue:
        k = (o['m']['campagne_id'], o['m']['liste_nom'])
        agg[k]['n'] += 1
        agg[k]['max_retard'] = max(agg[k]['max_retard'], (today - o['due'].date()).days)
        agg[k]['auto'] = o['m']['envoi_auto']
        agg[k]['val'] = o['m']['validation_relances']
        agg[k]['camp'] = o['m']['campagne_nom']
    print(f'{"campagne":34} {"liste":30} {"n":>4} {"retard":>7} {"envoi_auto":>10} {"valid_tg":>9}')
    print('-' * 94)
    for (cid, lnom), v in sorted(agg.items(), key=lambda kv: -kv[1]['n']):
        print(f'{v["camp"][:34]:34} {lnom[:30]:30} {v["n"]:>4} {v["max_retard"]:>6}j '
              f'{v["auto"]:>10} {v["val"]:>9}')
    n_auto = sum(1 for o in overdue if o['m']['envoi_auto'] == 1)
    print(f'\n  {n_auto}/{len(overdue)} relances échues sont dans une campagne envoi_auto=1 '
          f'(=> celles-là devraient partir SEULES).')

    # ═══ 3. état des lots Telegram ════════════════════════════════════════════
    print()
    print('=' * 94)
    print('3. ÉTAT DES LOTS DE VALIDATION TELEGRAM + DERNIERS REJOUÉS')
    print('=' * 94)
    info = conn.execute("SELECT name FROM sqlite_master WHERE type='table' "
                        "AND (name LIKE '%batch%' OR name LIKE '%relance%')").fetchall()
    for (t,) in info:
        cols = [c[1] for c in conn.execute(f'PRAGMA table_info({t})')]
        n = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
        print(f'  table {t} ({n} lignes) colonnes={cols}')
        for r in rows(conn, f'SELECT * FROM {t} ORDER BY 1 DESC LIMIT 6'):
            brief = {k: (str(v)[:40] if v is not None else None) for k, v in r.items()}
            print(f'     {brief}')

    conn.close()


if __name__ == '__main__':
    main()
