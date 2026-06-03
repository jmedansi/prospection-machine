import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT)

from database.connection import get_conn

def main():
    print("=== STARTING DATABASE CLEANUP ===")
    
    with get_conn() as conn:
        # 1. Clean up the stuck duplicate background campaigns
        cur = conn.execute(
            "UPDATE campagnes SET statut = 'cancelled', phase = 'cancelled' WHERE nom LIKE 'Background Top-up%' AND statut = 'actif'"
        )
        print(f"[SQLite] Terminated/Cancelled {cur.rowcount} stuck active background campaigns.")
        
        # 2. Insert or replace the toggle maps_auto_scrape to '0'
        conn.execute(
            "INSERT OR REPLACE INTO planning_settings (key, value) VALUES ('maps_auto_scrape', '0')"
        )
        print("[SQLite] Disabled Maps auto scraping: maps_auto_scrape set to '0' in planning_settings.")
        
        # 3. Reset scraping priority frequencies
        cur = conn.execute(
            "UPDATE scraping_priorities SET frequence_jours = 30 WHERE frequence_jours = 0"
        )
        print(f"[SQLite] Corrected execution frequencies for {cur.rowcount} scraping priorities (from 0 to 30 days).")
        
        conn.commit()
        
    print("=== DATABASE CLEANUP COMPLETED SUCCESSFULLY ===")

if __name__ == '__main__':
    main()
