
import sqlite3
import os
from datetime import datetime

db_path = "data/prospection.db"

def check_counts():
    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("--- COUNTS BY DATE (leads_bruts) ---")
    rows = cursor.execute("SELECT date(date_scraping), COUNT(*) FROM leads_bruts GROUP BY date(date_scraping) ORDER BY date(date_scraping) DESC LIMIT 10").fetchall()
    for row in rows:
        print(f"Date: {row[0]} | Count: {row[1]}")

    print("\n--- RECENT LEADS (last 5) ---")
    rows = cursor.execute("SELECT id, nom, email, telephone, date_scraping FROM leads_bruts ORDER BY id DESC LIMIT 5").fetchall()
    for row in rows:
        print(f"ID: {row[0]} | Nom: {row[1]} | E: {row[2]} | T: {row[3]} | Date: {row[4]}")

    conn.close()

if __name__ == "__main__":
    check_counts()
