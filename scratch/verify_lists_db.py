import sys

# Forcer UTF-8 sur stdout Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from database.connection import get_conn

with get_conn() as c:
    tables = c.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table' AND name LIKE 'lead_list%'"
    ).fetchall()
    for t in tables:
        sql_safe = (t['sql'] or '').encode('ascii', errors='replace').decode('ascii')
        print('TABLE:', t['name'])
        print(sql_safe)
        print()
    idx = c.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_list%'"
    ).fetchall()
    print('INDEX:', [i['name'] for i in idx])

    # Test CRUD rapide
    c.execute("INSERT OR IGNORE INTO lead_lists (nom, couleur, icone) VALUES ('TEST_LIST', '#6366f1', 'T')")
    c.commit()
    row = c.execute("SELECT id, nom, couleur, created_at FROM lead_lists WHERE nom='TEST_LIST'").fetchone()
    print('\nTest INSERT:', dict(row))
    c.execute("DELETE FROM lead_lists WHERE nom='TEST_LIST'")
    c.commit()
    print('Test DELETE: OK')
    print('\nVerification complete.')
