"""Suite du contrôle des délais — 3 points à confirmer avant conclusion.

1. Délai RÉELLEMENT observé par (campagne, position) : permet de savoir si les
   7 « envois trop tôt » sont de vraies violations ou si delai_jours a changé.
2. Pourquoi 60 relances sont échues : envoi_auto / validation_relances / lots.
3. Séquence de touches complète des 7 prospects signalés.
"""
import sqlite3, sys
from datetime import datetime, timedelta
from collections import defaultdict, Counter

sys.stdout.reconfigure(encoding='utf-8')
DB = 'file:D:/prospection-machine/data/prospection.db?mode=ro'
TOUCHES = ('initial', 'relance_1', 'relance_2', 'relance_3')
FLAGGED = (8737, 8738, 8740, 8743, 8744, 9015, 9016)


def add_business_days(start_dt, n_days):
    cur, added = start_dt, 0
    while added < n_days:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            added += 1
    return cur


def bdays(a, b):
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
        SELECT p.id, p.email, p.statut, l.nom AS liste_nom, l.campagne_id,
               c.nom AS campagne_nom, c.max_touches, c.envoi_auto, c.validation_relances
        FROM prospects p JOIN listes l ON l.id=p.liste_id
        JOIN campagnes c ON c.id=l.campagne_id""")}

    # ── 1. délai réel observé par (campagne, position) ───────────────────────
    print('=' * 80)
    print('1. DÉLAI RÉELLEMENT OBSERVÉ (jours ouvrés) par campagne / position')
    print('   Compare à la config ACTUELLE pour détecter un changement de règle.')
    print('=' * 80)
    obs = defaultdict(list)
    for pid, evs in ev_by_p.items():
        m = meta.get(pid)
        if not m:
            continue
        for i, ev in enumerate(evs):
            if ev['event_type'] == 'initial' or i == 0:
                continue
            pos = int(ev['event_type'].split('_')[1])
            cur, prev = parse(ev['created_at']), parse(evs[i - 1]['created_at'])
            if cur and prev:
                obs[(m['campagne_id'], m['campagne_nom'], pos)].append(bdays(prev, cur))

    print(f'{"campagne":40} {"pos":>4} {"config":>7} {"n":>4} {"min":>4} {"méd":>4} {"max":>4}  verdict')
    print('-' * 96)
    for (cid, cnom, pos), gaps in sorted(obs.items(), key=lambda kv: (kv[0][0], kv[0][2])):
        t = get_step(cid, pos)
        cfg = int(t['delai_jours']) if t and t.get('delai_jours') is not None else None
        g = sorted(gaps)
        med = g[len(g) // 2]
        verdict = ''
        if cfg is not None:
            if min(g) >= cfg:
                verdict = 'OK — aucun envoi avant échéance'
            elif med < cfg and max(g) <= cfg:
                verdict = f'⚠️ {sum(1 for x in g if x < cfg)}/{len(g)} en avance => delai était probablement {med}j AVANT'
            else:
                verdict = f'❌ {sum(1 for x in g if x < cfg)}/{len(g)} EN AVANCE de {cfg-min(g)}j'
        print(f'{cnom[:40]:40} {pos:>4} {str(cfg)+"j":>7} {len(g):>4} {min(g):>4} {med:>4} {max(g):>4}  {verdict}')

    # ── 2. pourquoi les relances sont échues ────────────────────────────────
    print()
    print('=' * 80)
    print('2. CONFIG D\'ENVOI DES CAMPAGNES (pourquoi des relances restent échues)')
    print('=' * 80)
    for c in rows(conn, """SELECT id, nom, envoi_auto, validation_relances, max_touches, statut
                           FROM campagnes ORDER BY id"""):
        print(f'  #{c["id"]:>3} {c["nom"][:44]:44} statut={c["statut"]:7} '
              f'envoi_auto={c["envoi_auto"]} validation_relances={c["validation_relances"]} '
              f'max_touches={c["max_touches"]}')

    print()
    print('  Kill-switch global + état des lots de validation Telegram :')
    try:
        for r in rows(conn, "SELECT key, value FROM planning_settings WHERE key LIKE '%auto%' OR key LIKE '%relance%'"):
            print(f'     {r["key"]:32} = {r["value"]}')
    except Exception as e:
        print(f'     (planning_settings : {e})')
    for t in ('relance_batches', 'relance_batch', 'batch_requests'):
        try:
            n = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
            print(f'     table {t} : {n} lignes')
            for r in rows(conn, f'SELECT status, COUNT(*) AS n FROM {t} GROUP BY status'):
                print(f'        {r["status"]}: {r["n"]}')
        except Exception:
            pass

    print()
    print('  Dernières tentatives d\'envoi (jobs / logs récents) :')
    for t in ('jobs', 'job_runs', 'scheduler_logs', 'logs', 'task_logs'):
        try:
            cols = [c[1] for c in conn.execute(f'PRAGMA table_info({t})')]
            n = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
            print(f'     table {t} : {n} lignes, colonnes={cols[:8]}')
        except Exception:
            pass

    # ── 3. séquence des 7 prospects signalés ───────────────────────────────
    print()
    print('=' * 80)
    print('3. SÉQUENCE COMPLÈTE DES 7 PROSPECTS SIGNALÉS « TROP TÔT »')
    print('=' * 80)
    for pid in FLAGGED:
        m = meta.get(pid)
        if not m:
            continue
        print(f'  prospect {pid} « {m["email"]} » statut={m["statut"]} '
              f'campagne « {m["campagne_nom"]} » liste « {m["liste_nom"]} »')
        evs = ev_by_p.get(pid, [])
        for i, ev in enumerate(evs):
            cur = parse(ev['created_at'])
            prev = parse(evs[i - 1]['created_at']) if i else None
            pos = int(ev['event_type'].split('_')[1]) if '_' in ev['event_type'] else 0
            if ev['event_type'] == 'initial' or i == 0:
                note = '(première touche)'
            else:
                t = get_step(m['campagne_id'], pos)
                dl = int(t['delai_jours']) if t and t.get('delai_jours') is not None else 0
                due = add_business_days(prev, dl)
                ecart = bdays(prev, cur)
                note = (f'délai config={dl}j ouvrés -> échéance {due:%Y-%m-%d} | '
                        f'réel={ecart}j ouvrés | '
                        + ('✅ respecté' if cur.date() >= due.date()
                           else f'❌ {bdays(cur, due)}j EN AVANCE'))
            print(f'     {ev["created_at"]}  {ev["event_type"]:11}  {note}')

    conn.close()


if __name__ == '__main__':
    main()
