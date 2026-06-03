import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT)

from database.connection import get_conn
from database.leads import get_leads_pending

def main():
    print("=== PENDING LEADS CHECKS ===")
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(id) FROM leads_bruts").fetchone()[0]
        pending = conn.execute("SELECT COUNT(id) FROM leads_bruts WHERE statut = 'en_attente'").fetchone()[0]
        scrape = conn.execute("SELECT COUNT(id) FROM leads_bruts WHERE statut = 'scrape'").fetchone()[0]
        sources = conn.execute("SELECT source, COUNT(id) FROM leads_bruts GROUP BY source").fetchall()
        
        print(f"Total leads: {total}")
        print(f"Pending ('en_attente') leads: {pending}")
        print(f"Scrape ('scrape') leads: {scrape}")
        print("Sources:")
        for s in sources:
            print(f"  - {s[0] or 'None'}: {s[1]}")
            
    print("\nPending via get_leads_pending(verify_smtp=False):")
    pending_list = get_leads_pending(verify_smtp=False)
    print(f"Count: {len(pending_list)}")
    if pending_list:
        print("First 3 pending leads:")
        for l in pending_list[:3]:
            print(f"  ID {l['id']}: {l['nom']} ({l['site_web']})")

if __name__ == '__main__':
    main()
