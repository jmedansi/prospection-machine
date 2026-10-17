"""Diagnostic relances v2 : doublons d'événements, incohérences statut<->événements, envois répétés."""
import sqlite3, sys, json
from collections import Counter, defaultdict
sys.stdout.reconfigure(encoding='utf-8')

DB = 'file:D:/prospection-machine/data/prospection.db?mode=ro'
TOUCHES = ('initial', 'relance_1', 'relance_2', 'relance_3')
# statut -> position ENVOYÉE max attendue
STATUT_POS = {'qualifie': 0, 'en_sequence': 1, 'relance_1': 2, 'relance_2': 3, 'relance_3': 4}
NEXT_POS = {'en_sequence': 1, 'relance_1': 2, 'relance_2': 3}


def rows(conn, sql, p=()):
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute(sql, p).fetchall()]


def main():
    conn = sqlite3.connect(DB, uri=True)

    print('=' * 78)
    print('A. ÉVÉNEMENTS DE TOUCHES PAR TYPE (toutes campagnes)')
    print('=' * 78)
    for r in rows(conn, """
        SELECT event_type, COUNT(*) AS n, COUNT(DISTINCT prospect_id) AS prosp
        FROM prospect_events WHERE event_type IN ('initial','relance_1','relance_2','relance_3')
        GROUP BY event_type ORDER BY event_type"""):
        print(f'  {r["event_type"]:12} événements={r["n"]:5}  prospects concernés={r["prosp"]:5}')

    print()
    print('=' * 78)
    print('B. ⚠️  MÊME TOUCHE ENVOYÉE PLUSIEURS FOIS (même prospect, même type)')
    print('=' * 78)
    dups = rows(conn, """
        SELECT prospect_id, event_type, COUNT(*) AS n,
               GROUP_CONCAT(id) AS event_ids,
               GROUP_CONCAT(created_at) AS dates
        FROM prospect_events
        WHERE event_type IN ('initial','relance_1','relance_2','relance_3')
        GROUP BY prospect_id, event_type HAVING COUNT(*) > 1
        ORDER BY n DESC""")
    print(f'  => {len(dups)} couples (prospect, touche) en double')
    by_type = Counter(d['event_type'] for d in dups)
    for t, c in by_type.most_common():
        print(f'     {t:12} : {c} prospects touchés {t} plusieurs fois')
    if dups:
        print('\n  Détail (10 premiers) :')
        for d in dups[:10]:
            det = rows(conn, """SELECT p.nom, p.email, p.statut, l.nom AS liste_nom
                                FROM prospects p LEFT JOIN listes l ON l.id=p.liste_id
                                WHERE p.id=?""", (d['prospect_id'],))
            info = det[0] if det else {}
            print(f'     prospect {d["prospect_id"]} « {info.get("nom")} » ({info.get("email")}) '
                  f'statut={info.get("statut")} liste={info.get("liste_nom")}')
            print(f'        {d["event_type"]} x{d["n"]} aux dates : {d["dates"]}')

    print()
    print('=' * 78)
    print('C. ⚠️  STATUT EN RETARD SUR LES ÉVÉNEMENTS (relance déjà envoyée')
    print('    mais le statut dit qu\'elle est encore à planifier)')
    print('=' * 78)
    ev_max = {}
    for r in rows(conn, """
        SELECT prospect_id, MAX(CASE event_type WHEN 'initial' THEN 1 WHEN 'relance_1' THEN 2
                              WHEN 'relance_2' THEN 3 WHEN 'relance_3' THEN 4 END) AS mx
        FROM prospect_events WHERE event_type IN ('initial','relance_1','relance_2','relance_3')
        GROUP BY prospect_id"""):
        ev_max[r['prospect_id']] = r['mx']

    incons = []
    for r in rows(conn, """SELECT p.id, p.nom, p.email, p.statut, p.liste_id, l.nom AS liste_nom,
                                  c.nom AS campagne_nom
                           FROM prospects p
                           JOIN listes l ON l.id=p.liste_id
                           JOIN campagnes c ON c.id=l.campagne_id
                           WHERE p.statut IN ('en_sequence','relance_1','relance_2','relance_3')
                             AND p.ecarte=0 AND p.ne_plus_contacter=0"""):
        sent = ev_max.get(r['id'], 0)
        statut_pos = STATUT_POS.get(r['statut'], 0)
        next_planned = NEXT_POS.get(r['statut'])
        if next_planned and sent >= next_planned:
            incons.append({**r, 'sent': sent, 'next_planned': next_planned})
    print(f'  => {len(incons)} prospects dont le calendrier reprojetterait une relance DÉJÀ envoyée')
    for r in incons[:15]:
        print(f'     prospect {r["id"]} « {r["nom"]} » statut={r["statut"]} '
              f'-> calendrier veut relance {r["next_planned"]} '
              f'MAIS touche max déjà envoyée = {r["sent"]} (liste « {r["liste_nom"]} »)')
    if len(incons) > 15:
        print(f'     ... et {len(incons)-15} autres')

    print()
    print('=' * 78)
    print('D. STATUT « EN AVANCE » SUR LES ÉVÉNEMENTS (statut avancé mais')
    print('    la touche correspondante n\'a jamais d\'événement)')
    print('=' * 78)
    ahead = []
    for r in rows(conn, """SELECT p.id, p.nom, p.email, p.statut, l.nom AS liste_nom
                           FROM prospects p JOIN listes l ON l.id=p.liste_id
                           WHERE p.statut IN ('relance_1','relance_2','relance_3')"""):
        sent = ev_max.get(r['id'], 0)
        statut_pos = STATUT_POS.get(r['statut'], 0)
        if sent < statut_pos:
            ahead.append({**r, 'sent': sent, 'statut_pos': statut_pos})
    print(f'  => {len(ahead)} prospects en avance sur leur historique')
    for r in ahead[:10]:
        print(f'     prospect {r["id"]} « {r["nom"]} » statut={r["statut"]} '
              f'(implique {r["statut_pos"]} touches) mais seulement {r["sent"]} événement(s) '
              f'(liste « {r["liste_nom"]} »)')

    print()
    print('=' * 78)
    print('E. ENVOIS RÉELS EN DOUBLE (emails_envoyes)')
    print('=' * 78)
    try:
        d2 = rows(conn, """
            SELECT lead_id, relance_type, COUNT(*) AS n, GROUP_CONCAT(date_envoi) AS dates
            FROM emails_envoyes
            WHERE lead_id IS NOT NULL
            GROUP BY lead_id, relance_type HAVING COUNT(*) > 1
            ORDER BY n DESC""")
        print(f'  => {len(d2)} (prospect, type de relance) envoyés plusieurs fois')
        for d in d2[:15]:
            det = rows(conn, "SELECT nom, email FROM prospects WHERE id=?", (d['lead_id'],))
            info = det[0] if det else {}
            print(f'     prospect {d["lead_id"]} « {info.get("nom")} » ({info.get("email")}) '
                  f'relance_type={d["relance_type"]!r} x{d["n"]}')
            print(f'        dates : {d["dates"]}')
    except Exception as e:
        print(f'  (erreur : {e})')

    print()
    print('=' * 78)
    print('F. MAX_TOUCHES DÉPASSÉ')
    print('=' * 78)
    over = rows(conn, """
        SELECT p.id, p.nom, p.statut, c.max_touches, l.nom AS liste_nom,
               SUM(CASE WHEN ev.event_type IN ('initial','relance_1','relance_2','relance_3') THEN 1 ELSE 0 END) AS touches
        FROM prospects p
        JOIN listes l ON l.id=p.liste_id JOIN campagnes c ON c.id=l.campagne_id
        LEFT JOIN prospect_events ev ON ev.prospect_id=p.id
        GROUP BY p.id HAVING touches > c.max_touches""")
    print(f'  => {len(over)} prospects ayant reçu plus de touches que max_touches')
    for r in over[:10]:
        print(f'     prospect {r["id"]} « {r["nom"]} » touches={r["touches"]} '
              f'max={r["max_touches"]} statut={r["statut"]} liste={r["liste_nom"]}')

    conn.close()


if __name__ == '__main__':
    main()
