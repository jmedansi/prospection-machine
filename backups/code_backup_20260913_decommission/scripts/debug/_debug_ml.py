import sqlite3
conn = sqlite3.connect('data/prospection.db')
c = conn.cursor()

# ALL leads with >50 avis, grouped by notes status and secteur
c.execute("""
SELECT 
  secteur,
  SUM(CASE WHEN notes IS NULL OR notes = '' THEN 1 ELSE 0 END) as empty,
  SUM(CASE WHEN notes = '(mentions legales introuvables)' THEN 1 ELSE 0 END) as introuvables,
  SUM(CASE WHEN notes LIKE '%timeout%' OR notes LIKE '%erreur%' THEN 1 ELSE 0 END) as errors,
  SUM(CASE WHEN notes IS NOT NULL AND notes != '' 
       AND notes != '(mentions legales introuvables)'
       AND notes NOT LIKE '%timeout%' AND notes NOT LIKE '%erreur%' THEN 1 ELSE 0 END) as has_data,
  COUNT(*) as total
FROM leads_bruts
WHERE nb_avis > 50
  AND site_web IS NOT NULL AND site_web != ''
GROUP BY secteur
ORDER BY total DESC
""")
print(f"{'Secteur':<25} {'Total':<6} {'Empty':<6} {'Introuv':<8} {'Errors':<7} {'Data':<6}")
print('-'*58)
for r in c.fetchall():
    print(f"{r[0]:<25} {r[5]:<6} {r[1]:<6} {r[2]:<8} {r[3]:<7} {r[4]:<6}")

conn.close()
