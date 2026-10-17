"""Diagnostic v2 : doublons de prospects + impact sur les planifications (relances)."""
import sqlite3, sys, io
sys.stdout.reconfigure(encoding='utf-8')

DB = 'file:D:/prospection-machine/data/prospection.db?mode=ro'
PROTECTED = {'rdv_obtenu', 'ne_plus_contacter', 'adresse_invalide'}  # états finaux


def rows(conn, sql, p=()):
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute(sql, p).fetchall()]


def main():
    conn = sqlite3.connect(DB, uri=True)

    print('=' * 74)
    print('A. LISTES CONCERNÉES (doublons d\'email dans la même liste)')
    print('=' * 74)
    dups = rows(conn, '''
        SELECT p.liste_id, LOWER(TRIM(p.email)) AS email, COUNT(*) AS n
        FROM prospects p
        WHERE p.email IS NOT NULL AND TRIM(p.email) != ''
        GROUP BY liste_id, LOWER(TRIM(email))
        HAVING COUNT(*) > 1
    ''')
    by_liste = {}
    for d in dups:
        by_liste.setdefault(d['liste_id'], []).append(d)
    print(f'{"liste":>6} {"nom liste":38} {"campagne":26} {"nb groupes":>10} {"nb doublons":>11}')
    print('-' * 95)
    tot_groups = tot_extra = 0
    for lid, g in sorted(by_liste.items(), key=lambda kv: -len(kv[1])):
        info = rows(conn, '''SELECT l.nom AS ln, c.nom AS cn
                             FROM listes l LEFT JOIN campagnes c ON c.id = l.campagne_id
                             WHERE l.id = ?''', (lid,))
        ln = (info[0]['ln'] if info else '?')[:38]
        cn = (info[0]['cn'] if info else '?')[:26]
        extra = sum(x['n'] - 1 for x in g)
        tot_groups += len(g); tot_extra += extra
        print(f'{lid:>6} {ln:38} {cn:26} {len(g):>10} {extra:>11}')
    print('-' * 95)
    print(f'{"TOTAL":>6} {"":38} {"":26} {tot_groups:>10} {tot_extra:>11}')

    print()
    print('=' * 74)
    print('B. IMPACT PLANIFICATION — statut des prospects doublons')
    print('=' * 74)
    st = rows(conn, '''
        SELECT p.statut, COUNT(*) AS n
        FROM prospects p
        JOIN (SELECT liste_id, LOWER(TRIM(email)) AS e, COUNT(*) AS c
              FROM prospects
              WHERE email IS NOT NULL AND TRIM(email) != ''
              GROUP BY liste_id, LOWER(TRIM(email)) HAVING COUNT(*) > 1) d
          ON d.liste_id = p.liste_id AND LOWER(TRIM(p.email)) = d.e
        GROUP BY p.statut ORDER BY n DESC
    ''')
    print(f'  {"statut":24} {"nb prospects doublonnés":>24}')
    for r in st:
        flag = '  <-- RISQUE RELANCE DOUBLE' if r['statut'] and any(k in r['statut'] for k in ('en_sequence', 'relance')) else ''
        print(f'  {str(r["statut"]):24} {r["n"]:>24}{flag}')

    print()
    print('=' * 74)
    print('C. DOUBLONS DÉJÀ ENVOYÉS (emails_envoyes) — double contact déjà réel')
    print('=' * 74)
    try:
        sent = rows(conn, '''
            SELECT LOWER(TRIM(p.email)) AS email, p.liste_id, COUNT(DISTINCT p.id) AS nb_prospects,
                   COUNT(e.id) AS nb_envois
            FROM prospects p
            JOIN (SELECT liste_id, LOWER(TRIM(email)) AS e, COUNT(*) AS c
                  FROM prospects
                  WHERE email IS NOT NULL AND TRIM(email) != ''
                  GROUP BY liste_id, LOWER(TRIM(email)) HAVING COUNT(*) > 1) d
              ON d.liste_id = p.liste_id AND LOWER(TRIM(p.email)) = d.e
            JOIN emails_envoyes e ON e.lead_id = p.id
            GROUP BY LOWER(TRIM(p.email)), p.liste_id
            HAVING COUNT(e.id) > 1
            ORDER BY nb_envois DESC
        ''')
        print(f'  => {len(sent)} adresses déjà contactées PLUSIEURS FOIS')
        for r in sent[:15]:
            print(f'     {r["email"]:42} liste={r["liste_id"]:>5} prospects={r["nb_prospects"]} envois={r["nb_envois"]}')
        if len(sent) > 15:
            print(f'     ... et {len(sent)-15} autres')
    except Exception as e:
        print(f'  (table emails_envoyes : {e})')

    print()
    print('=' * 74)
    print('D. ÉTATS FINAUX PARMI LES DOUBLONS (protégés vs supprimables)')
    print('=' * 74)
    prot = rows(conn, '''
        SELECT p.statut, COUNT(*) AS n
        FROM prospects p
        JOIN (SELECT liste_id, LOWER(TRIM(email)) AS e, COUNT(*) AS c
              FROM prospects
              WHERE email IS NOT NULL AND TRIM(email) != ''
              GROUP BY liste_id, LOWER(TRIM(email)) HAVING COUNT(*) > 1) d
          ON d.liste_id = p.liste_id AND LOWER(TRIM(p.email)) = d.e
        WHERE p.statut IN ('rdv_obtenu','ne_plus_contacter','adresse_invalide')
        GROUP BY p.statut
    ''')
    for r in prot:
        print(f'  {r["statut"]:24} {r["n"]:>6}  (état final -> conserver impérativement)')

    print()
    print('=' * 74)
    print('E. QUALITÉ DES DONNÉES DES COPIES (laquelle garder ?)')
    print('=' * 74)
    q1 = rows(conn, '''
        SELECT SUM(CASE WHEN email IS NULL OR TRIM(email)='' THEN 1 ELSE 0 END) AS sans_email,
               SUM(CASE WHEN telephone IS NULL OR TRIM(telephone)='' THEN 1 ELSE 0 END) AS sans_tel,
               SUM(CASE WHEN site_web IS NULL OR TRIM(site_web)='' THEN 1 ELSE 0 END) AS sans_site,
               COUNT(*) AS total
        FROM (SELECT p.* FROM prospects p
              JOIN (SELECT liste_id, LOWER(TRIM(email)) AS e, COUNT(*) AS c
                    FROM prospects
                    WHERE email IS NOT NULL AND TRIM(email) != ''
                    GROUP BY liste_id, LOWER(TRIM(email)) HAVING COUNT(*) > 1) d
                ON d.liste_id = p.liste_id AND LOWER(TRIM(p.email)) = d.e)
    ''')
    r0 = q1[0]
    print(f'  Sur les {r0["total"]} prospects doublonnés :')
    print(f'    sans téléphone : {r0["sans_tel"]}')
    print(f'    sans site_web   : {r0["sans_site"]}')

    conn.close()


if __name__ == '__main__':
    main()
