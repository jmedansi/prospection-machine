import subprocess
import sqlite3
import os
import sys

def extract_git_db(commit, output_path):
    """Extrait un fichier binaire depuis git en mode binaire pur."""
    result = subprocess.run(
        ['git', 'cat-file', 'blob', f'{commit}:data/prospection.db'],
        capture_output=True,  # récupère stdout en bytes bruts
        cwd=r'd:\prospection-machine'
    )
    if result.returncode != 0:
        print(f"[ERREUR] git cat-file: {result.stderr.decode()}")
        return False
    with open(output_path, 'wb') as f:
        f.write(result.stdout)
    size = os.path.getsize(output_path)
    print(f"[OK] {output_path} - {size/1024/1024:.2f} MB extrait")
    return True

def inspect_db(path, label):
    print(f"\n=== {label} ===")
    size = os.path.getsize(path)
    print(f"  Taille: {size/1024/1024:.2f} MB")
    try:
        conn = sqlite3.connect(path)
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        for t in tables:
            c = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
            print(f"  {t}: {c} lignes")
        if 'leads_bruts' in tables:
            dr = conn.execute("SELECT MIN(date_scraping), MAX(date_scraping) FROM leads_bruts").fetchone()
            print(f"  Date range: {dr[0]} -> {dr[1]}")
        conn.close()
        return 'leads_bruts' in tables
    except Exception as e:
        print(f"  ERREUR: {e}")
        return False

# Extraire les deux commits
print("Extraction des DBs depuis git...")
ok1 = extract_git_db('7224933', r'd:\prospection-machine\scratch\git_db_7224933.db')
ok2 = extract_git_db('523cba0', r'd:\prospection-machine\scratch\git_db_523cba0.db')

# Inspecter
if ok1:
    inspect_db(r'd:\prospection-machine\scratch\git_db_7224933.db', 'commit 7224933 (le plus recent)')
if ok2:
    inspect_db(r'd:\prospection-machine\scratch\git_db_523cba0.db', 'commit 523cba0 (plus ancien)')
inspect_db(r'd:\prospection-machine\data\prospection.db', 'current (endommagee)')
