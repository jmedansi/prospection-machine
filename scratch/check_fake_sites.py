from database import get_conn

FAKE_SITE_PATTERNS = ['wa.me', 'facebook.com', 'instagram.com', 't.me', 'twitter.com', 'linkedin.com']

with get_conn() as conn:
    # Leads avec URL non-site (wa.me, facebook, instagram, etc.)
    rows = conn.execute("""
        SELECT id, nom, site_web, statut FROM leads_bruts
        WHERE (site_web LIKE '%wa.me%'
           OR site_web LIKE '%facebook.com%'
           OR site_web LIKE '%instagram.com%'
           OR site_web LIKE '%t.me%'
           OR site_web LIKE '%twitter.com%')
        LIMIT 20
    """).fetchall()
    print(f"Leads avec faux site (reseaux sociaux/whatsapp): {len(rows)}")
    for r in rows:
        d = dict(r)
        print(f"  ID={d['id']} | {d['nom'][:40]} | site_web={d['site_web']} | statut={d['statut']}")

    # Aussi vérifier le filtre actuel dans le code
    print("\n--- Vérification filtre auditeur pour lead 1599 ---")
    row = conn.execute("SELECT id, nom, site_web, statut FROM leads_bruts WHERE id = 1599").fetchone()
    if row:
        r = dict(row)
        site = (r.get('site_web') or '').strip().lower()
        filtered_out = site.startswith(('http://', 'https://'))
        print(f"site_web = '{r['site_web']}'")
        print(f"Filtré comme 'avec site' (exclu de l'audit no-site): {filtered_out}")
        print(f"-> Résultat: {'EXCLU (bug!)' if filtered_out else 'INCLUS dans l audit'}")
