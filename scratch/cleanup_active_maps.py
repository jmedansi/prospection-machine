import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT)

from database.connection import get_conn

def main():
    print("=== CANCELLING ALL ACTIVE MAPS CAMPAIGNS ===")
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE campagnes SET statut = 'cancelled', phase = 'cancelled' WHERE source = 'maps' AND statut = 'actif'"
        )
        print(f"[SQLite] Cancelled {cur.rowcount} active Maps campaigns.")
        conn.commit()
    print("=== DONE ===")

if __name__ == '__main__':
    main()
