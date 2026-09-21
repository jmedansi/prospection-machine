import sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from database.connection import get_conn
conn = get_conn()

# Check for potential Bénin leads with wrong pays
print("=== Leads potentiellement Bénin (pays='fr' ou NULL) ===")
rows = conn.execute("""
    SELECT lb.id, lb.nom, lb.ville, lb.pays, lb.secteur, lb.site_web, lb.lien_maps
    FROM leads_bruts lb
    WHERE (lb.ville LIKE '%Cotonou%' OR lb.ville LIKE '%Porto-Novo%' OR lb.ville LIKE '%Parakou%'
           OR lb.ville LIKE '%Abomey%' OR lb.ville LIKE '%Bohicon%' OR lb.ville LIKE '%Bénin%'
           OR lb.ville LIKE '%Benin%')
    ORDER BY lb.ville, lb.nom
""").fetchall()
for r in rows:
    pays_val = r[3] or 'NULL'
    sect_val = r[4] or ''
    site_val = r[5] or ''
    maps_val = r[6] or ''
    print(f"  #{r[0]:5d} {r[1]:30s} {r[2] or '':20s} pays={pays_val:5s} sect={sect_val:20s} site={site_val:30s} maps={maps_val:20s}")
print(f"  Total : {len(rows)}")

# Check distinct pays values
print("\n=== Valeurs de 'pays' distinctes ===")
rows2 = conn.execute("SELECT pays, COUNT(*) FROM leads_bruts GROUP BY pays").fetchall()
for r in rows2:
    print(f"  {r[0] or 'NULL':10s} {r[1]:5d}")

# Check distinct villes for Bénin
print("\n=== Villes des leads Bénin (pays='bj') ===")
rows3 = conn.execute("""
    SELECT ville, COUNT(*) FROM leads_bruts WHERE pays='bj' GROUP BY ville ORDER BY COUNT(*) DESC
""").fetchall()
for r in rows3:
    print(f"  {r[0] or 'NULL':30s} {r[1]:4d}")

conn.close()
