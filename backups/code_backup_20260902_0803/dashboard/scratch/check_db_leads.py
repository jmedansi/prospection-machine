
import sqlite3
import os

db_path = "data/prospection.db"

def check_leads():
    if not os.path.exists(db_path):
        print(f"Database {db_path} not found")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("--- LAST 10 LEADS IN LEADS_BRUTS ---")
    rows = cursor.execute("SELECT id, nom, site_web, email, telephone, date_scraping FROM leads_bruts ORDER BY id DESC LIMIT 10").fetchall()
    for row in rows:
        print(f"ID: {row['id']} | {row['nom']} | Email: {row['email'] or 'MISSING'} | Tel: {row['telephone'] or 'MISSING'}")

    print("\n--- TABLE INFO: leads_audites ---")
    cursor.execute("PRAGMA table_info(leads_audites)")
    cols = [c[1] for c in cursor.fetchall()]
    print(f"Columns: {cols}")

    print("\n--- LAST 5 ROWS IN leads_audites ---")
    audits = cursor.execute("SELECT * FROM leads_audites ORDER BY id DESC LIMIT 5").fetchall()
    for a in audits:
        print(dict(a))

    conn.close()

if __name__ == "__main__":
    check_leads()
