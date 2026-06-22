import sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from database.connection import get_conn
conn = get_conn()

# Fix pays for all Cotonou leads that are incorrectly tagged as 'fr'
result = conn.execute("""
    UPDATE leads_bruts
    SET pays = 'bj'
    WHERE (ville LIKE '%Cotonou%' OR ville LIKE '%Porto-Novo%' OR ville LIKE '%Parakou%'
           OR ville LIKE '%Abomey%' OR ville LIKE '%Bohicon%')
      AND (pays IS NULL OR pays != 'bj')
""")
print(f"Leads mis a jour: {result.rowcount}")
conn.commit()

# Verify
rows = conn.execute("SELECT pays, COUNT(*) FROM leads_bruts WHERE pays='bj' GROUP BY pays").fetchall()
for r in rows:
    print(f"  {r[0]}: {r[1]}")

# Count Bénin leads without site
rows2 = conn.execute("""
    SELECT secteur, COUNT(*) as cnt
    FROM leads_bruts
    WHERE pays = 'bj'
      AND (site_web IS NULL OR site_web = '')
      AND statut NOT IN ('archive', 'bounced', 'desabonne')
      AND lien_maps IS NOT NULL AND lien_maps != ''
    GROUP BY secteur
    ORDER BY cnt DESC
""").fetchall()
total = 0
print("\n=== Leads Bénin sans site (avec lien_maps) ===")
for r in rows2:
    print(f"  {r[0] or 'sans secteur':30s} {r[1]:4d}")
    total += r[1]
print(f"  {'TOTAL':30s} {total:4d}")

conn.close()
