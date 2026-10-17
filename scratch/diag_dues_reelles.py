"""Répond à : « ces relances sont-elles RÉELLEMENT dues, ou artefact de planification ? »

A. Traçabilité individuelle des relances dues : dernière touche RÉELLE -> échéance.
B. Contre-vérification : un envoi réel existe-t-il dans emails_envoyes SANS event ?
   (si oui => la relance est faussement « due », event manquant)
C. Reproduction EXACTE du calendrier : combien de relances par prospect tombent
   dans le passé quand une touche précédente a pris du retard (« programmés 3 fois »).
D. Doublons réels dans la projection (même prospect + même position + même date).
"""
import sqlite3, sys
from datetime import datetime, timedelta, date
from collections import defaultdict, Counter

sys.stdout.reconfigure(encoding='utf-8')
DB = 'file:D:/prospection-machine/data/prospection.db?mode=ro'
NEXT_POS = {'en_sequence': 1, 'relance_1': 2, 'relance_2': 3}
DEFAULT_DELAYS = {1: 3, 2: 7, 3: 14}


def add_business_days(start_dt, n_days):
    """IDENTIQUE core.orchestration.add_business_days."""
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

    # ── événements de touche + meta ─────────────────────────────────────────
    ev_by_p = defaultdict(list)
    for r in conn.execute("""SELECT ev.prospect_id, ev.event_type, ev.created_at
                             FROM prospect_events ev
                             WHERE ev.event_type IN ('initial','relance_1','relance_2','relance_3')
                             ORDER BY ev.prospect_id, ev.created_at, ev.id"""):
        ev_by_p[r['prospect_id']].append(dict(r))

    meta = {r['id']: dict(r) for r in rows(conn, """
        SELECT p.id, p.email, p.statut, p.liste_id, l.nom AS liste_nom, l.type AS liste_type,
               l.campagne_id, c.nom AS campagne_nom, c.max_touches, c.envoi_auto
        FROM prospects p JOIN listes l ON l.id=p.liste_id
        JOIN campagnes c ON c.id=l.campagne_id""")}

    today = datetime.utcnow().date()

    # ═══ A. traçabilité des dues ══════════════════════════════════════════════
    dues = []
    for pid, evs in ev_by_p.items():
        m = meta.get(pid)
        if not m or not evs or m['statut'] not in NEXT_POS:
            continue
        if m['liste_type'] == 'corbeille':
            continue
        pos = NEXT_POS[m['statut']]
        t = get_step(m['campagne_id'], pos)
        if not t:
            continue
        last = evs[-1]
        last_dt = parse(last['created_at'])
        if not last_dt:
            continue
        delai = int(t['delai_jours'] or 0)
        due = add_business_days(last_dt, delai)
        if due.date() <= today:
            dues.append({'pid': pid, 'm': m, 'pos': pos, 'delai': delai,
                         'last': last, 'last_dt': last_dt, 'due': due,
                         'retard': (today - due.date()).days})

    print('=' * 104)
    print(f'A. LES {len(dues)} RELANCES DUES — TRACÉ COMPLET (dernière touche -> échéance)')
    print('=' * 104)
    print(f'{"prospect":>8} {"statut":13} {"pos":>4} {"dernière TOUCHE réelle":26} '
          f'{"delai":>5} {"échéance":12} {"retard":>7}')
    print('-' * 104)
    for d in sorted(dues, key=lambda x: x['due'])[:25]:
        print(f'{d["pid"]:>8} {d["m"]["statut"]:13} {d["pos"]:>4} '
              f'{d["last"]["created_at"][:19] + " " + d["last"]["event_type"]:26} '
              f'{d["delai"]:>4}j {d["due"].strftime("%Y-%m-%d"):12} {d["retard"]:>6}j')
    if len(dues) > 25:
        print(f'  ... et {len(dues) - 25} autres')

    # cohérence interne : la touche précédente existe-t-elle vraiment ?
    sans_precedente = [d for d in dues if len(ev_by_p[d['pid']]) < 2]
    print(f'\n  Prospects dont la touche précédente N’EXISTE PAS dans le journal : '
          f'{len(sans_precedente)}  '
          f'{"(toutes dues sont étayées par 2 touches réelles)" if not sans_precedente else ""}')

    # ═══ B. envoi réel sans event ? ═══════════════════════════════════════════
    print()
    print('=' * 104)
    print('B. CONTRE-VÉRIF — un envoi RÉEL (emails_envoyes) existe-t-il APRÈS la')
    print('   dernière touche, sans événement ? (=> relance « due » à tort)')
    print('=' * 104)
    sent_after = []
    for d in dues:
        r = rows(conn, """SELECT date_envoi, email_objet FROM emails_envoyes
                          WHERE lead_id = ? AND date_envoi > ?
                          ORDER BY date_envoi""",
                 (d['pid'], d['last']['created_at']))
        if r:
            sent_after.append((d, r))
    print(f'  => {len(sent_after)} relances « dues » ont pourtant un envoi réel postérieur')
    for d, r in sent_after[:15]:
        print(f'     prospect {d["pid"]} statut={d["m"]["statut"]} '
              f'-> {len(r)} envoi(s) sans event : {r[0]["date_envoi"]} …')
    if not sent_after:
        print('     ✅ AUCUN — les 59 dues sont bien SANS envoi réel. Elles sont réellement dues.')

    # ═══ C. reproduction du calendrier — effet « programmés 3 fois » ══════════
    print()
    print('=' * 104)
    print('C. CALENDRIER — projection enCHAÎNÉE (reproduction exacte de la route)')
    print('   Quand une touche prend du retard, les touches SUIVANTES héritent du')
    print('   décalage et TOMBENT DANS LE PASSÉ => elles s’affichent « en retard »')
    print('   PLUSIEURS FOIS pour le même prospect.')
    print('=' * 104)

    proj = defaultdict(list)   # pid -> [(pos, date, statut)]
    for pid, evs in ev_by_p.items():
        m = meta.get(pid)
        if not m or not evs or m['statut'] not in NEXT_POS or m['liste_type'] == 'corbeille':
            continue
        last_dt = parse(evs[-1]['created_at'])
        if not last_dt:
            continue
        cur_pos = NEXT_POS[m['statut']]
        max_touches = int(m.get('max_touches') or 3)
        prev = last_dt
        for pos in range(cur_pos, max_touches):
            t = get_step(m['campagne_id'], pos)
            delai = int(t['delai_jours']) if t and t.get('delai_jours') is not None \
                else DEFAULT_DELAYS.get(pos, 3)
            sched = add_business_days(prev, delai)
            st = ('due' if sched.date() <= today else 'planned') if pos == cur_pos else 'planned'
            proj[pid].append({'pos': pos, 'd': sched.date(), 'st': st, 'delai': delai})
            prev = sched

    multi = {pid: v for pid, v in proj.items() if len(v) > 1}
    past_multi = {pid: [x for x in v if x['d'] <= today] for pid, v in proj.items()}
    past_multi = {pid: v for pid, v in past_multi.items() if len(v) > 1}

    print(f'  Prospects avec projection multiple (>1 relance affichée) : {len(multi)}')
    print(f'  Prospects avec PLUSIEURS relances affichées DANS LE PASSÉ : {len(past_multi)}')
    print(f'    => c’est exactement l’effet « programmés 3 fois » que tu décris.\n')

    print('  Exemples (les plus en retard) :')
    for pid, v in sorted(past_multi.items(), key=lambda kv: -len(kv[1]))[:8]:
        m = meta[pid]
        print(f'     prospect {pid} « {(m["email"] or "")[:34]:34} » statut={m["statut"]:12} '
              f'liste « {m["liste_nom"][:30]} »')
        for x in v:
            tag = 'DUE (vraie)' if x['pos'] == NEXT_POS[m['statut']] else \
                  'projetée depuis une date DÉJÀ PASSÉE (cascade)'
            print(f'        relance_{x["pos"]} prévue {x["d"]:%Y-%m-%d} '
                  f'({(today - x["d"]).days:>2}j avant) [{x["st"]}]  <- {tag}')

    # total de projections passées vs vraies dues
    n_past = sum(1 for v in proj.values() for x in v if x['d'] <= today)
    print(f'\n  TOTAL relances affichées avec une date passée : {n_past}')
    print(f'  dont VRAIMENT dues (position suivante)      : {len(dues)}')
    print(f'  dont CASCADE de projection (à venir, jamais reprogrammées) : {n_past - len(dues)}')

    # ═══ D. vrais doublons ════════════════════════════════════════════════════
    print()
    print('=' * 104)
    print('D. DOUBLONS RÉELS dans la projection (même prospect + même position)')
    print('=' * 104)
    dupes = [(pid, pos) for pid, v in proj.items()
             for pos, n in Counter(x['pos'] for x in v).items() if n > 1]
    print(f'  => {len(dupes)} doublons (un prospect ne peut avoir qu’UNE projection '
          f'par position dans cette route)')
    if not dupes:
        print('     ✅ AUCUN — la projection ne duplique jamais une même relance.')

    # doublons événements passés (relance envoyée 2x déjà connu)
    ev_dup = rows(conn, """SELECT prospect_id, event_type, COUNT(*) AS n
                           FROM prospect_events
                           WHERE event_type IN ('initial','relance_1','relance_2','relance_3')
                           GROUP BY prospect_id, event_type HAVING COUNT(*) > 1""")
    print(f'\n  Événements de touche dupliqués (envoi réellement répété) : {len(ev_dup)} couples')
    for e in ev_dup:
        if e['event_type'] != 'initial':
            print(f'     prospect {e["prospect_id"]} : {e["event_type"]} envoyé {e["n"]} fois')

    conn.close()


if __name__ == '__main__':
    main()
