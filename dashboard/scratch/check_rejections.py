
import sqlite3
import os

db_path = "data/prospection.db"

def check_rejections():
    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("--- RECENT REJECTIONS (approuve = -1) ---")
    rows = cursor.execute("""
        SELECT lb.nom, la.problem_details, la.rapport_resume, la.date_audit 
        FROM leads_audites la 
        JOIN leads_bruts lb ON la.lead_id = lb.id 
        WHERE la.approuve = -1 
        ORDER BY la.id DESC LIMIT 10
    """).fetchall()
    
    if not rows:
        print("No rejected leads (approuve = -1) found in the last 10 entries.")
    else:
        for row in rows:
            print(f"Nom: {row['nom']} | Date: {row['date_audit']} | Problem: {row['problem_details']} | Resume: {row['rapport_resume']}")

    print("\n--- LEADS WITH NO EMAIL/PHONE (Rejection at Scraping) ---")
    # Actually, if they are rejected at scraping, they are NOT in the DB.
    # But maybe they are in leads_bruts but marked as 'rejete'?
    # Let's check the statut column.
    cursor.execute("SELECT DISTINCT statut FROM leads_bruts")
    statuts = [r[0] for r in cursor.fetchall()]
    print(f"Statuts in leads_bruts: {statuts}")

    if 'rejete' in statuts:
        rej = cursor.execute("SELECT nom, email, telephone FROM leads_bruts WHERE statut = 'rejete' LIMIT 5").fetchall()
        for r in rej:
            print(f"REJETE: {r['nom']} | E: {r['email']} | T: {r['telephone']}")

    conn.close()

if __name__ == "__main__":
    check_rejections()
