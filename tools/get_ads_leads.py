# Quick helper: list up to 10 pending leads with 'ads' in source
import sys
import os
# Ensure project root is on sys.path when this script is run from tools/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.connection import get_conn

def main():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, nom, site_web, source FROM leads_bruts WHERE statut='en_attente' AND (source LIKE '%ads%' OR source LIKE '%google%') ORDER BY id DESC LIMIT 10"
        ).fetchall()
        if not rows:
            print("NO_LEADS")
            return
        ids = [str(r['id']) for r in rows]
        for r in rows:
            print(f"{r['id']}\t{r['nom']}\t{r['site_web']}\t{r['source']}")
        print("IDS:" + ",".join(ids))

if __name__ == '__main__':
    main()
