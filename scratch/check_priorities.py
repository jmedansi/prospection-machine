import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT)

from database.connection import get_conn

def main():
    print("--- SCRAPING PRIORITIES (TOP 20) ---")
    with get_conn() as conn:
        rows = conn.execute("SELECT id, secteur, keyword, ville, limit_leads, priorite, actif, frequence_jours, source, derniere_execution FROM scraping_priorities ORDER BY priorite ASC, derniere_execution ASC LIMIT 20").fetchall()
        for r in rows:
            print(dict(r))

if __name__ == '__main__':
    main()
