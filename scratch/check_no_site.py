from database import get_conn
import sys

with get_conn() as conn:
    rows = conn.execute("SELECT id, nom, site_web, statut FROM leads_bruts WHERE (site_web IS NULL OR site_web = '') AND statut IN ('en_attente', 'scrape', 'scraped') LIMIT 10").fetchall()
    print(f"Found {len(rows)} leads without site web pending audit:")
    for r in rows:
        print(dict(r))
