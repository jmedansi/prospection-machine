import sqlite3
import os

db_path = 'd:/prospection-machine/data/prospection.db'
if not os.path.exists(db_path):
    db_path = 'prospection.db'

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# We want to see if we have keywords/categories matching:
# 1. Immobilier: "agence immobilière", "agent immobilier", etc.
# 2. Courtage: "courtier", "cabinet de courtage", etc.
# 3. Concessionnaires auto: "concessionnaire", "garage", etc.
# 4. Cliniques esthétiques: "esthétique", "botox", "chirurgie", etc.
# 5. Écoles de formation: "formation", "école", etc.

rules = {
    "immobilier": ["immobil", "immo"],
    "courtage": ["courtier", "courtage"],
    "concessionnaires_auto": ["concessionnaire", "garage", "auto"],
    "cliniques_esthetiques": ["esthétique", "clinique esth", "centre esth"],
    "ecoles_formation": ["formation", "école", "ecole"]
}

print("--- ANALYZING UNTAGGED LEADS ---")
for sector, keywords in rules.items():
    print(f"\nSector: {sector}")
    # Build a query with LIKE for keywords
    like_clauses = " OR ".join([f"mot_cle LIKE ?" for _ in keywords])
    like_clauses_cat = " OR ".join([f"category LIKE ?" for _ in keywords])
    
    params = [f"%{k}%" for k in keywords] * 2
    
    query = f"""
        SELECT COUNT(*) as count 
        FROM leads_bruts 
        WHERE secteur IS NULL AND ({like_clauses} OR {like_clauses_cat})
    """
    row = conn.execute(query, params).fetchone()
    print(f"  Found {row['count']} untagged leads matching sector criteria in leads_bruts.")
    
    # Let's see a sample of terms if found
    if row['count'] > 0:
        sample_query = f"""
            SELECT mot_cle, category, COUNT(*) as c
            FROM leads_bruts
            WHERE secteur IS NULL AND ({like_clauses} OR {like_clauses_cat})
            GROUP BY mot_cle, category
            ORDER BY c DESC
            LIMIT 5
        """
        samples = conn.execute(sample_query, params).fetchall()
        print("  Top matches:")
        for s in samples:
            print(f"    - keyword: {s['mot_cle']} | category: {s['category']} | count: {s['c']}")

conn.close()
