import sqlite3, os

dbs = {
    '7224933': r'd:\prospection-machine\scratch\git_db_7224933.db',
    '523cba0': r'd:\prospection-machine\scratch\git_db_523cba0.db',
    'current': r'd:\prospection-machine\data\prospection.db',
}

for label, db in dbs.items():
    size = os.path.getsize(db)
    print(f"\n=== commit {label} ({size/1024/1024:.2f} MB) ===")
    try:
        conn = sqlite3.connect(db)
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        for t in tables:
            c = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
            print(f"  {t}: {c} rows")
        if 'leads_bruts' in tables:
            dr = conn.execute("SELECT MIN(date_scraping), MAX(date_scraping) FROM leads_bruts").fetchone()
            print(f"  Date range leads_bruts: {dr[0]} → {dr[1]}")
        conn.close()
    except Exception as e:
        print(f"  ERREUR: {e}")
