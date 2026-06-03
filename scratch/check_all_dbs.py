import sqlite3
import os

dbs = [
    r'd:\prospection-machine\prospection.db',
    r'd:\prospection-machine\data\prospection.db',
    r'd:\prospection-machine\data\database.sqlite',
    r'd:\prospection-machine\database.db',
]

# Also check backup dirs
backup_dirs = [
    r'd:\prospection-machine\backups\pre-refact-2026-04-16',
    r'd:\prospection-machine\backups\v4-cleanup-temp',
    r'd:\prospection-machine\backups\v4-cleanup-temp_20260507_023235',
]
for bdir in backup_dirs:
    if os.path.isdir(bdir):
        for f in os.listdir(bdir):
            if f.endswith('.db') or f.endswith('.sqlite'):
                dbs.append(os.path.join(bdir, f))

for db in dbs:
    if os.path.exists(db):
        size = os.path.getsize(db)
        try:
            conn = sqlite3.connect(db)
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            counts = {}
            for t in tables:
                try:
                    counts[t] = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
                except Exception as e2:
                    counts[t] = f'ERR:{e2}'
            conn.close()
            print(f"\n=== {db} ({size/1024/1024:.2f} MB) ===")
            for t, c in counts.items():
                print(f"  {t}: {c} rows")
            if not counts:
                print("  (aucune table)")
        except Exception as e:
            print(f"\n=== {db} ({size/1024/1024:.2f} MB) === ERREUR: {e}")
    else:
        print(f"\n[ABSENT] {db}")
