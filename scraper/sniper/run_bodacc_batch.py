"""Run BODACC scanner for multiple dates with progress tracking"""
import sys, os, logging, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
logging.basicConfig(level=logging.INFO, format="%(message)s")

from sniper.bodacc_scanner import scan_daily
from database.connection import get_conn

# Get dates already scanned
with get_conn() as conn:
    existing = set()
    cur = conn.execute("SELECT DISTINCT json_extract(donnees_audit, '$.bodacc_date') FROM leads_bruts WHERE source='bodacc' AND donnees_audit IS NOT NULL")
    for r in cur.fetchall():
        d = r[0]
        if d:
            existing.add(d)
    print(f"Already have BODACC data for {len(existing)} dates: {sorted(existing)[-5:] if existing else 'none'}")

# Dates to scan (last 30 days, skip existing)
from datetime import date, timedelta
dates = []
for i in range(1, 31):
    d = date.today() - timedelta(days=i)
    ds = d.isoformat()
    if ds not in existing:
        dates.append(ds)

print(f"Scanning {len(dates)} new dates...")
total_inserted = 0
for i, ds in enumerate(dates, 1):
    print(f"\n--- [{i}/{len(dates)}] {ds} ---")
    start = time.time()
    try:
        result = scan_daily(ds)
        elapsed = time.time() - start
        ins = result.get("inserted", 0)
        total_inserted += ins
        print(f"  -> {ins} inserted, {result.get('scanned',0)} scanned, {result.get('filtered',0)} filtered ({elapsed:.0f}s)")
    except Exception as e:
        print(f"  -> ERROR: {e}")

print(f"\n=== DONE: {total_inserted} total leads inserted ===")
