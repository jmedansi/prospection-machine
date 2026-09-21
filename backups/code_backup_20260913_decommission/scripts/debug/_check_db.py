import sqlite3

conn = sqlite3.connect('data/prospection.db')
c = conn.cursor()

# Stats finales Ads par secteur
c.execute("""
SELECT secteur, 
  COUNT(*) as total,
  SUM(CASE WHEN email IS NOT NULL AND email != '' AND email != '-' THEN 1 ELSE 0 END) as with_email,
  SUM(CASE WHEN prenom_gerant IS NOT NULL AND prenom_gerant != '' AND prenom_gerant != '-' THEN 1 ELSE 0 END) as with_ceo
FROM leads_bruts
WHERE source = 'ads'
GROUP BY secteur
ORDER BY secteur
""")
rows = c.fetchall()
print(f"{'Secteur':<30} {'Total':<6} {'Email':<8} {'CEO':<8}")
print('-'*52)
for r in rows:
    print(f"{r[0]:<30} {r[1]:<6} {r[2]:<8} {r[3]:<8}")

# Voir les incomplets restants
c.execute("""
SELECT id, nom, email, prenom_gerant FROM leads_bruts
WHERE source = 'ads'
  AND (email IS NULL OR email = '' OR email = '-')
  AND (prenom_gerant IS NULL OR prenom_gerant = '' OR prenom_gerant = '-')
""")
remaining = c.fetchall()
print(f"\nCompletement vides (ni email ni CEO): {len(remaining)}")

# Voir les Maps avec nb_avis > 50 pour Phase 3
c.execute("""
SELECT secteur, COUNT(*) FROM leads_bruts
WHERE (source IS NULL OR source != 'ads') AND nb_avis > 50
  AND site_web IS NOT NULL AND site_web != ''
  AND (notes IS NULL OR notes = '')
GROUP BY secteur
ORDER BY COUNT(*) DESC
""")
rows = c.fetchall()
total_ml = sum(r[1] for r in rows)
print(f"\nPhase 3 ML Maps: {total_ml} leads avec >50 avis et pas encore de notes")
for r in rows:
    print(f"  {r[0]}: {r[1]}")

conn.close()
