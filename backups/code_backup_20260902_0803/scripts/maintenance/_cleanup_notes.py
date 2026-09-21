import sqlite3, re
conn = sqlite3.connect('data/prospection.db')
c = conn.cursor()

NOISE = [
    "mentions legales introuvables", "timeout", "erreur", "rien trouve",
    "il n", "aucune personne", "sont pas explicitement", "pas de personnes responsables",
    "personne physique", "pas d information", "pas de responsable",
    "aucune information", "aucun renseignement",
    "non pr", "non disponible",
    "null null", "null - null", "non communique",
    "ne sont pas",
    "n est pas",
    "n a pas ete",
    "n est pas mentionne",
    "n est pas clairement",
    "pas trouve",
    "non trouve",
]

where_clauses = [f"notes LIKE '%{p}%'" for p in NOISE]
where_not = " AND notes NOT LIKE '%' ESCAPE '\\'"
# Actually just use simple approach
placeholders_str = " OR ".join(f"notes LIKE '%{p}%'" for p in NOISE)

sql = f"""
SELECT id, secteur, substr(notes,1,120) as debut FROM leads_bruts
WHERE site_web IS NOT NULL AND site_web != ''
  AND notes IS NOT NULL AND notes != ''
  AND NOT ({placeholders_str})
ORDER BY id
LIMIT 50
"""
c.execute(sql)
print("=== NOTES GARDEES (reelles) ===")
count = 0
for r in c.fetchall():
    print(f"  #{r[0]} {r[1]:<25} {r[2]}")
    count += 1
print(f"  ({count} affichees)")

# Also count
sql_count = f"""
SELECT COUNT(*) FROM leads_bruts
WHERE site_web IS NOT NULL AND site_web != ''
  AND notes IS NOT NULL AND notes != ''
  AND NOT ({placeholders_str})
"""
c.execute(sql_count)
print(f"\nTotal notes reelles: {c.fetchone()[0]}")

sql_count2 = f"""
SELECT COUNT(*) FROM leads_bruts
WHERE site_web IS NOT NULL AND site_web != ''
  AND (notes IS NULL OR notes = ''
    OR ({placeholders_str}))
"""
c.execute(sql_count2)
print(f"Total a resetter: {c.fetchone()[0]}")

conn.close()
