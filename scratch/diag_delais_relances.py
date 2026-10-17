"""Contrôle des DÉLAIS de relances (jours ouvrés) — lecture seule.

Recalcule, à l'identique du moteur (`delai_non_atteint` / `relances_due`), si :
  A. chaque relance DÉJÀ ENVOYÉE respectait son délai (pas d'envoi trop tôt)
  B. les relances à VENIR sont correctement planifiées (et non bloquées à jamais)
  C. la config des templates (delai_jours) est saine
"""
import sqlite3, sys
from datetime import datetime, timedelta
from collections import defaultdict, Counter

sys.stdout.reconfigure(encoding='utf-8')

DB = 'file:D:/prospection-machine/data/prospection.db?mode=ro'
TOUCHES = ('initial', 'relance_1', 'relance_2', 'relance_3')
NEXT_POS = {'en_sequence': 1, 'relance_1': 2, 'relance_2': 3}
STATUT_POS = {'qualifie': 0, 'en_sequence': 1, 'relance_1': 2, 'relance_2': 3,
              'relance_3': 4, 'sans_reponse': 4}
DEFAULT_DELAYS = {1: 3, 2: 7, 3: 14}


# ── répliques exactes du code moteur ──────────────────────────────────────────
def add_business_days(start_dt, n_days):
    """core.orchestration.add_business_days (lun-ven uniquement)."""
    cur, added = start_dt, 0
    while added < n_days:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            added += 1
    return cur


def business_days_between(a, b):
    """Nombre de jours ouvrés POSITIFS de a (exclu) à b (inclus). 0 si b <= a."""
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


def fr_day(dt):
    return ['lun', 'mar', 'mer', 'jeu', 'ven', 'sam', 'dim'][dt.weekday()]


def main():
    conn = sqlite3.connect(DB, uri=True)
    conn.row_factory = sqlite3.Row

    # ── templates : résolution dédié > générique, actif=1 (get_step) ─────────
    steps = {}
    for r in conn.execute("""SELECT * FROM sequence_templates WHERE actif = 1
                             ORDER BY COALESCE(campagne_id, 999999), position, delai_jours"""):
        d = dict(r)
        key = (d['campagne_id'], d['position'])
        # la 1re ligne pour la clé gagne (trip position, delai_jours) -> identique à get_step
        steps.setdefault(key, d)

    def get_step(cid, pos):
        return steps.get((cid, pos)) or steps.get((None, pos))

    print('=' * 80)
    print('C. CONFIG DES TEMPLATES (delai_jours par campagne / position)')
    print('=' * 80)
    by_c = defaultdict(dict)
    for (cid, pos), d in steps.items():
        by_c[cid][pos] = d['delai_jours']
    for cid, posmap in sorted(by_c.items(), key=lambda kv: (kv[0] is not None, kv[0] or 0)):
        nom = 'GÉNÉRIQUE' if cid is None else f'campagne #{cid}'
        if cid is not None:
            row = conn.execute('SELECT nom FROM campagnes WHERE id=?', (cid,)).fetchone()
            nom = f'campagne #{cid} « {row[0]} »' if row else nom
        txt = '  '.join(f'pos{p}={posmap[p]}j' for p in sorted(posmap))
        flags = []
        for p, v in posmap.items():
            if v is None or int(v) <= 0:
                flags.append(f'⚠️ pos{p} delai={v} (relance DÈS LE PROCHAIN JOUR OUVRÉ)')
        print(f'  {nom:46} {txt}{"   " + " ".join(flags) if flags else ""}')
    missing = [p for p in (1, 2, 3) if get_step(None, p) is None]
    if missing:
        print(f'  ⚠️ positions SANS aucun template générique actif : {missing}')

    # ── campagnes en activité ────────────────────────────────────────────────
    camps = {r['id']: dict(r) for r in
             conn.execute("SELECT id, nom, max_touches FROM campagnes WHERE statut='actif'")}

    # ── tous les événements de touche, par prospect ──────────────────────────
    ev_by_p = defaultdict(list)
    for r in conn.execute(f"""SELECT ev.id, ev.prospect_id, ev.event_type, ev.created_at
                              FROM prospect_events ev
                              WHERE ev.event_type IN ({','.join('?'*len(TOUCHES))})
                              ORDER BY ev.prospect_id, ev.created_at, ev.id""", TOUCHES):
        ev_by_p[r['prospect_id']].append(dict(r))

    meta = {r['id']: dict(r) for r in conn.execute("""
        SELECT p.id, p.nom, p.email, p.statut, p.liste_id, l.nom AS liste_nom,
               l.campagne_id, c.nom AS campagne_nom, c.max_touches, l.type AS liste_type
        FROM prospects p JOIN listes l ON l.id = p.liste_id
        JOIN campagnes c ON c.id = l.campagne_id""")}

    # ══════════════════════════════════════════════════════════════════════════
    print()
    print('=' * 80)
    print('A. RELANCES DÉJÀ ENVOYÉES — le délai après la dernière touche est-il')
    print('   respecté ? (échéance = dernière touche + delai_jours en JOURS OUVRÉS)')
    print('=' * 80)

    too_early, weekend_send, no_template, evaluable = [], [], [], 0
    gaps = []
    for pid, evs in ev_by_p.items():
        m = meta.get(pid)
        if not m:
            continue
        cid = m['campagne_id']
        for i, ev in enumerate(evs):
            if ev['event_type'] == 'initial':
                continue
            pos = int(ev['event_type'].split('_')[1])
            t = get_step(cid, pos)
            cur = parse(ev['created_at'])
            prev = parse(evs[i - 1]['created_at']) if i > 0 else None
            if cur is None:
                continue
            if cur.weekday() >= 5:
                weekend_send.append((m, ev, cur))
            if not t:
                no_template.append((m, ev, pos))
                continue
            if prev is None:
                continue
            delai = int(t.get('delai_jours') or 0)
            due = add_business_days(prev, delai)
            evaluable += 1
            if cur.date() < due.date():
                avance = business_days_between(cur, due)
                too_early.append((m, ev, prev, due, cur, delai, avance))
            gaps.append(business_days_between(prev, cur))

    print(f'  Relances évaluables : {evaluable}')
    if gaps:
        print(f'  Délai réel observé (jours ouvrés entre 2 touches) : '
              f'min={min(gaps)}  médiane={sorted(gaps)[len(gaps)//2]}  max={max(gaps)}')

    print()
    print(f'  ❌ ENVOIS TROP TÔTS (avant échéance) : {len(too_early)}')
    for m, ev, prev, due, cur, delai, avance in too_early[:25]:
        print(f'     prospect {m["id"]:>6} « {(m["email"] or "")[:34]:34} » {ev["event_type"]}')
        print(f'        dernière touche {prev:%Y-%m-%d %a} + {delai}j ouvrés '
              f'=> échéance {due:%Y-%m-%d %a}')
        print(f'        ENVOYÉ LE {cur:%Y-%m-%d %a}  => {avance} jour(s) ouvré(s) EN AVANCE')
        print(f'        liste « {m["liste_nom"]} » / campagne « {m["campagne_nom"]} »')
    if len(too_early) > 25:
        print(f'     ... et {len(too_early)-25} autres')
    if not too_early:
        print('     ✅ aucun — toutes les relances envoyées sont postérieures à leur échéance.')

    print()
    print(f'  ❌ ENVOIS LE WEEK-END (samedi/dimanche) : {len(weekend_send)}')
    for m, ev, cur in weekend_send[:15]:
        print(f'     prospect {m["id"]:>6} {ev["event_type"]} le {cur:%Y-%m-%d} ({fr_day(cur)}) '
              f'— {m["email"]}')
    if not weekend_send:
        print('     ✅ aucun.')

    print()
    print(f'  ⚠️ RELANCES ENVOYÉES SANS TEMPLATE DE POSITION : {len(no_template)}')
    for m, ev, pos in no_template[:15]:
        print(f'     prospect {m["id"]:>6} {ev["event_type"]} (pos {pos}) '
              f'campagne « {m["campagne_nom"]} »')
    if not no_template:
        print('     ✅ aucun.')

    # ══════════════════════════════════════════════════════════════════════════
    print()
    print('=' * 80)
    print('B. RELANCES À VENIR — projection identique au calendrier')
    print('=' * 80)

    today = datetime.utcnow().date()
    planned_all = []
    no_tpl_planned = []
    weekend_planned = []
    overdue = []

    for pid, evs in ev_by_p.items():
        m = meta.get(pid)
        if not m or not evs:
            continue
        if m['statut'] not in NEXT_POS:
            continue
        if m['liste_type'] == 'corbeille':
            continue
        last = parse(evs[-1]['created_at'])
        if not last:
            continue
        cur_pos = NEXT_POS[m['statut']]
        max_touches = int(m.get('max_touches') or 3)
        prev_dt = last
        for pos in range(cur_pos, max_touches):
            t = get_step(m['campagne_id'], pos)
            delai = int(t['delai_jours']) if t and t.get('delai_jours') is not None \
                else DEFAULT_DELAYS.get(pos, 3)
            sched = add_business_days(prev_dt, delai)
            item = {'pid': pid, 'pos': pos, 'sched': sched, 'delai': delai,
                    'template': t is not None, 'm': m}
            planned_all.append(item)
            if pos == cur_pos and sched.date() <= today:
                overdue.append(item)
            if t is None:
                no_tpl_planned.append(item)
            if sched.weekday() >= 5:
                weekend_planned.append(item)
            prev_dt = sched

    futurs = [p for p in planned_all if p['sched'].date() > today]
    passes = [p for p in planned_all if p['sched'].date() <= today]

    print(f'  Relances projetées au total : {len(planned_all)} '
          f'(dont {len(futurs)} à venir, {len(passes)} échues)')
    by_pos = Counter(p['pos'] for p in planned_all)
    print('  Par position : ' + '  '.join(f'relance_{k}=v{by_pos[k]}' for k in sorted(by_pos)))
    by_jour = Counter(p['sched'].strftime('%a') for p in planned_all)
    print('  Jour de la semaine prévu : ' + '  '.join(f'{k}={by_jour[k]}' for k in
          ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] if k in by_jour))

    print()
    print(f'  ⚠️ PROJETÉES UN JOUR NON OUVRÉ : {len(weekend_planned)}')
    if not weekend_planned:
        print('     ✅ aucune — add_business_days ne tombe jamais sur samedi/dimanche '
              '(dès que delai > 0).')
    else:
        for it in weekend_planned[:10]:
            print(f'     prospect {it["pid"]} relance_{it["pos"]} '
                  f'prévue {it["sched"]:%Y-%m-%d} ({fr_day(it["sched"])}) delai={it["delai"]}')

    print()
    print(f'  ❌ RELANCES ÉCHUES MAIS PAS ENVOYÉES (« due » aujourd’hui) : {len(overdue)}')
    by_l = Counter(o['m']['liste_nom'] for o in overdue)
    for k, v in by_l.most_common():
        print(f'     {k:46} {v:>4}')
    retard_max = max(((today - o['sched'].date()).days for o in overdue), default=0)
    if overdue:
        print(f'     retard max : {retard_max} jour(s) civil(s)')
        print('     Exemples :')
        for o in sorted(overdue, key=lambda x: x['sched'])[:12]:
            print(f'       prospect {o["pid"]:>6} « {(o["m"]["email"] or "")[:32]:32} » '
                  f'statut={o["m"]["statut"]:12} relance_{o["pos"]} '
                  f'échue depuis {o["sched"]:%Y-%m-%d} ({(today - o["sched"].date()).days}j)')

    print()
    print(f'  ❌ RELANCES AFFICHÉES DANS LE CALENDRIER MAIS JAMAIS ENVOYABLES '
          f'(position sans template actif) : {len(no_tpl_planned)}')
    if no_tpl_planned:
        for it in no_tpl_planned[:15]:
            print(f'     prospect {it["pid"]:>6} relance_{it["pos"]} '
                  f'prévue {it["sched"]:%Y-%m-%d} campagne « {it["m"]["campagne_nom"]} »'
                  f'  <-- le moteur n\'a AUCUN template => n\'enverra JAMAIS')
    else:
        print('     ✅ aucune — toutes les positions projetées ont un template actif.')

    # ── cohérence max_touches ────────────────────────────────────────────────
    print()
    print('=' * 80)
    print('D. max_touches PAR CAMPAGNE (le cycle se ferme-t-il correctement ?)')
    print('=' * 80)
    for cid, c in sorted(camps.items()):
        n_touch = len([1 for pid, evs in ev_by_p.items()
                       if meta.get(pid, {}).get('campagne_id') == cid])
        print(f'  campagne #{cid} « {c["nom"][:40]:40} » max_touches={c["max_touches"]} '
              f'({n_touch} prospects avec historique)')

    conn.close()


if __name__ == '__main__':
    main()
