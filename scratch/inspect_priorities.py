import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT)

from database.connection import get_conn

def main():
    print("--- SCRAPING PRIORITIES ---")
    with get_conn() as conn:
        rows = conn.execute("SELECT id, secteur, keyword, ville, priorite, actif, frequence_jours, derniere_execution FROM scraping_priorities").fetchall()
        for r in rows:
            print(dict(r))

if __name__ == '__main__':
    main()
