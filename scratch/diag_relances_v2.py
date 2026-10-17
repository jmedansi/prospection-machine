"""V2 corrigé — relances. Filtre les faux positifs de la v1 (sections C et E)."""
import sqlite3, sys
from datetime import datetime
from collections import Counter
sys.stdout.reconfigure(encoding='utf-8')

DB = 'file:D:/prospection-machine/data/prospection.db?mode=ro'
# position (1-based) de chaque touche
POS = {'initial': 1, 'relance_1': 2, 'relance_2': 3, 'relance_3': 4}
# statut -> position de la prochaine relance À PLANIFIER
NEXT_POS = {'en_sequence': 1, 'relance_1': 2, 'relance_2': 3}


def rows(conn, sql, p=()):
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute(sql, p).fetchall()]


def main():
    conn = sqlite3.connect(DB, uri=True)

    # ── touche max réellement envoyée par prospect ────────────────────────
    mx = {r['prospect_id']: r['mx'] for r in rows(conn, """
        SELECT prospect_id, MAX(CASE event_type WHEN 'initial' THEN 1 WHEN 'relance_1' THEN 2
                              WHEN 'relance_2' THEN 3 WHEN 'relance_3' THEN 4 END) AS mx
        FROM prospect_events WHERE event_type IN ('initial','relance_1','relance_2','relance_3')
        GROUP BY prospect_id""")}

    print('=' * 78)
    print('C CORRIGÉ — RELANCE DÉJÀ ENVOYÉE MAIS ENCORE PLANIFIÉE')
    print('   (relance de position P déjà présente en événement, alors que le')
    print('    statut dit que P est la prochaine à envoyer)')
    print('=' * 78)
    bad = []
    for r in rows(conn, """SELECT p.id, p.nom, p.email, p.statut, l.nom AS liste_nom, c.nom AS campagne_nom
                           FROM prospects p
                           JOIN listes l ON l.id=p.liste_id JOIN campagnes c ON c.id=l.campagne_id
                           WHERE p.statut IN ('en_sequence','relance_1','relance_2','relance_3')
                             AND p.ecarte=0 AND p.ne_plus_contacter=0
                             AND (l.type IS NULL OR l.type != 'corbeille')"""):
        next_p = NEXT_POS.get(r['statut'])
        if not next_p:
            continue
        sent = mx.get(r['id'], 0)
        # la relance de position `next_p` est déjà envoyée si sent >= next_p + 1
        if sent >= next_p + 1:
            bad.append({**r, 'sent': sent, 'next_p': next_p})
    print(f'  => {len(bad)} prospects concernés (les {len(rows(conn,"SELECT 1")) if False else 0}...)')
    by_liste = Counter(r['liste_nom'] for r in bad)
    print('  Par liste :')
    for k, v in by_liste.most_common():
        print(f'     {k:44} {v:>4}')
    if bad:
        print('  Exemples :')
        for r in bad[:10]:
            print(f'     prospect {r["id"]} « {r["nom"]} » statut={r["statut"]} '
                  f'-> calendrier planifie relance_{r["next_p"]} '
                  f'MAIS relance_{r["next_p"]} déjà envoyée (touche max={r["sent"]})')

    print()
    print('=' * 78)
    print('E CORRIGÉ — ENVOIS RÉELLEMENT RÉPÉTÉS (mêmes prospects, même jour,')
    print('   quelques secondes/minutes d\'écart = vraie duplication d\'envoi)')
    print('=' * 78)
    allrows = rows(conn, """
        SELECT e.id, e.lead_id, e.date_envoi, e.email_destinataire, e.email_objet,
               p.nom, p.email AS p_email
        FROM emails_envoyes e LEFT JOIN prospects p ON p.id = e.lead_id
        WHERE e.date_envoi IS NOT NULL
        ORDER BY e.lead_id, e.date_envoi""")

    def parse(d):
        for f in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M'):
            try:
                return datetime.strptime(str(d)[:19], f)
            except ValueError:
                pass
        return None

    by_lead = {}
    for r in allrows:
        if r['lead_id'] is None:
            continue
        by_lead.setdefault(r['lead_id'], []).append(r)

    dups = []
    for lid, lst in by_lead.items():
        parsed = [(r, parse(r['date_envoi'])) for r in lst]
        parsed = [(r, d) for r, d in parsed if d]
        parsed.sort(key=lambda x: x[1])
        for i in range(1, len(parsed)):
            prev_r, prev_d = parsed[i - 1]
            cur_r, cur_d = parsed[i]
            gap = (cur_d - prev_d).total_seconds()
            if gap <= 3600:  # moins d'une heure après le précédent => duplication
                dups.append({'lead_id': lid, 'nom': cur_r['nom'], 'email': cur_r['p_email'],
                             'dest': cur_r['email_destinataire'], 'gap_s': gap,
                             'd1': prev_d, 'd2': cur_d, 'liste': None})

    print(f'  => {len(dups)} envois rattrapés dans l\'heure qui suivait déjà un envoi')
    gapneg = [d for d in dups if d['gap_s'] <= 0]
    print(f'     dont {len(gapneg)} à écart nul/négatif (mêmes secondes)')
    for d in sorted(dups, key=lambda x: x['gap_s'])[:20]:
        print(f'     prospect {d["lead_id"]} « {d["nom"]} » ({d["dest"]}) '
              f'gap={d["gap_s"]:.0f}s')
        print(f'        {d["d1"]}  puis  {d["d2"]}')
    if len(dups) > 20:
        print(f'     ... et {len(dups)-20} autres')

    # répartition par jour (pic de duplication)
    print()
    print('  Répartition par jour des envois rapprochés :')
    for k, v in Counter(d['d2'].strftime('%Y-%m-%d') for d in dups).most_common():
        print(f'     {k} : {v}')

    print()
    print('=' * 78)
    print('B — INITIAL ENVOYÉ PLUSIEURS FOIS (récapitulatif chiffré)')
    print('=' * 78)
    d2 = rows(conn, """
        SELECT prospect_id, COUNT(*) AS n, MIN(created_at) AS d1, MAX(created_at) AS d2
        FROM prospect_events WHERE event_type='initial'
        GROUP BY prospect_id HAVING COUNT(*) > 1 ORDER BY n DESC""")
    print(f'  => {len(d2)} prospects ont reçu l\'initial PLUSIEURS FOIS '
          f'({sum(r["n"] for r in d2) - len(d2)} envois initiaux en trop)')
    for r in d2[:12]:
        det = rows(conn, """SELECT p.nom, p.email, l.nom AS liste_nom, p.statut
                            FROM prospects p LEFT JOIN listes l ON l.id=p.liste_id
                            WHERE p.id=?""", (r['prospect_id'],))
        i = det[0] if det else {}
        print(f'     x{r["n"]} {i.get("email")} « {i.get("nom")} » '
              f'liste=« {i.get("liste_nom")} » statut={i.get("statut")}')
        print(f'        du {r["d1"]} au {r["d2"]}')

    print()
    print('=' * 78)
    print('RÉCAPITULATIF DES RELANCES (2 prospects seulement)')
    print('=' * 78)
    r2 = rows(conn, """
        SELECT prospect_id, COUNT(*) AS n, GROUP_CONCAT(created_at) AS dates
        FROM prospect_events WHERE event_type='relance_2'
        GROUP BY prospect_id HAVING COUNT(*) > 1""")
    for r in r2:
        det = rows(conn, """SELECT p.nom, p.email, p.statut, l.nom AS liste_nom
                            FROM prospects p LEFT JOIN listes l ON l.id=p.liste_id
                            WHERE p.id=?""", (r['prospect_id'],))
        i = det[0] if det else {}
        print(f'  prospect {r["prospect_id"]} « {i.get("nom")} » ({i.get("email")}) '
              f'statut={i.get("statut")} liste=« {i.get("liste_nom")} »')
        print(f'     relance_2 envoyée {r["n"]} fois : {r["dates"]}')

    conn.close()


if __name__ == '__main__':
    main()
