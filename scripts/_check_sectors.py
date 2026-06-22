import sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from database.connection import get_conn
conn = get_conn()

# Check sectors for Bénin leads without site
rows = conn.execute("""
    SELECT secteur, COUNT(*) as cnt
    FROM leads_bruts
    WHERE pays = 'bj'
      AND (site_web IS NULL OR site_web = '')
      AND statut NOT IN ('archive', 'bounced', 'desabonne')
    GROUP BY secteur
    ORDER BY cnt DESC
""").fetchall()

print("=== Secteurs des leads Bénin sans site ===")
for r in rows:
    print(f"  {r[0] or 'NULL':30s} {r[1]:4d}")

# Total
total = sum(r[1] for r in rows)
print(f"\n  TOTAL: {total}")

# Check if we can auto-categorize based on nom/mot_cle
rows2 = conn.execute("""
    SELECT id, nom, mot_cle, secteur
    FROM leads_bruts
    WHERE pays = 'bj'
      AND (site_web IS NULL OR site_web = '')
      AND statut NOT IN ('archive', 'bounced', 'desabonne')
    ORDER BY secteur, nom
""").fetchall()

print("\n=== Apercu des leads ===")
for r in rows2[:20]:
    print(f"  #{r[0]:5d} {r[1]:40s} mot_cle={r[2] or '':30s} secteur={r[3] or 'NULL'}")

conn.close()
