"""Diagnostic lecture seule : doublons et anomalies dans les listes / planifications v2."""
import sqlite3

DB = 'file:D:/prospection-machine/data/prospection.db?mode=ro'


def q(conn, sql, params=()):
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def scalar(conn, sql, params=()):
    r = conn.execute(sql, params).fetchone()
    return r[0] if r else None


def main():
    conn = sqlite3.connect(DB, uri=True)

    print('=' * 70)
    print('INVENTAIRE')
    print('=' * 70)
    for t in ['campagnes', 'listes', 'prospects', 'prospect_events',
              'suppression_list', 'mailboxes', 'emails_envoyes']:
        try:
            print(f'  {t:20s} : {scalar(conn, f"SELECT COUNT(*) FROM {t}")} rows')
        except Exception as e:
            print(f'  {t:20s} : ABSENTE ({e})')

    # ── 1. Prospects sans liste / sans campagne (orphelins) ────────────────
    print()
    print('=' * 70)
    print('1. PROSPECTS ORPHELINS (règle dorée : jamais sans liste ni campagne)')
    print('=' * 70)
    try:
        rows = q(conn, '''
            SELECT p.id, p.nom, p.email, p.liste_id
            FROM prospects p
            LEFT JOIN listes l ON l.id = p.liste_id
            WHERE p.liste_id IS NULL OR l.id IS NULL
        ''')
        print(f'  => {len(rows)} prospects sans liste valide')
        for r in rows[:20]:
            print(f'     id={r["id"]} liste_id={r["liste_id"]} nom={r["nom"]!r} email={r["email"]!r}')
        if len(rows) > 20:
            print(f'     ... et {len(rows)-20} autres')
    except Exception as e:
        print(f'  erreur: {e}')

    # ── 2. Doublons d'email DANS la même liste ─────────────────────────────
    print()
    print('=' * 70)
    print('2. DOUBLONS D\'EMAIL DANS LA MEME LISTE')
    print('=' * 70)
    try:
        rows = q(conn, '''
            SELECT liste_id, email, COUNT(*) AS n,
                   GROUP_CONCAT(p.id) AS ids, MAX(p.nom) AS nom
            FROM prospects p
            WHERE p.email IS NOT NULL AND TRIM(p.email) != ''
            GROUP BY liste_id, LOWER(TRIM(email))
            HAVING COUNT(*) > 1
            ORDER BY n DESC
        ''')
        total_dups = sum(r['n'] - 1 for r in rows)
        print(f'  => {len(rows)} emails en doublon, soit {total_dups} doublons en trop')
        for r in rows[:30]:
            print(f'     liste={r["liste_id"]} x{r["n"]} {r["email"]!r} nom={r["nom"]!r} ids={r["ids"]}')
        if len(rows) > 30:
            print(f'     ... et {len(rows)-30} autres groupes')
    except Exception as e:
        print(f'  erreur: {e}')

    # ── 3. Doublons d'email À TRAVERS les listes (même campagne) ───────────
    print()
    print('=' * 70)
    print('3. MEME EMAIL DANS PLUSIEURS LISTES')
    print('=' * 70)
    try:
        rows = q(conn, '''
            SELECT LOWER(TRIM(email)) AS email, COUNT(DISTINCT liste_id) AS nb_listes,
                   COUNT(*) AS total, GROUP_CONCAT(DISTINCT p.liste_id) AS listes,
                   MAX(p.nom) AS nom
            FROM prospects p
            WHERE p.email IS NOT NULL AND TRIM(p.email) != ''
            GROUP BY LOWER(TRIM(email))
            HAVING COUNT(DISTINCT liste_id) > 1
            ORDER BY nb_listes DESC, total DESC
        ''')
        print(f'  => {len(rows)} emails répartis dans plusieurs listes')
        for r in rows[:25]:
            print(f'     {r["email"]!r} nom={r["nom"]!r} listes={r["listes"]} (x{r["total"]})')
        if len(rows) > 25:
            print(f'     ... et {len(rows)-25} autres')
    except Exception as e:
        print(f'  erreur: {e}')

    # ── 4. Doublons exacts (nom+email+liste) ───────────────────────────────
    print()
    print('=' * 70)
    print('4. DOUBLONS EXACTS (liste + email + nom)')
    print('=' * 70)
    try:
        rows = q(conn, '''
            SELECT liste_id, LOWER(TRIM(COALESCE(email,''))) AS email,
                   LOWER(TRIM(COALESCE(nom,''))) AS nom, COUNT(*) AS n,
                   GROUP_CONCAT(p.id) AS ids
            FROM prospects p
            WHERE p.email IS NOT NULL AND TRIM(p.email) != ''
            GROUP BY liste_id, LOWER(TRIM(email)), LOWER(TRIM(nom))
            HAVING COUNT(*) > 1
            ORDER BY n DESC
        ''')
        print(f'  => {len(rows)} doublons stricts')
        for r in rows[:20]:
            print(f'     liste={r["liste_id"]} x{r["n"]} {r["email"]!r} / {r["nom"]!r} ids={r["ids"]}')
    except Exception as e:
        print(f'  erreur: {e}')

    conn.close()


if __name__ == '__main__':
    main()
