
import sqlite3
import os

db_path = "data/prospection.db"

def check_sources_today():
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT source, COUNT(*) FROM leads_bruts WHERE date(date_scraping) = '2026-05-01' GROUP BY source").fetchall()
    for row in rows:
        print(f"Source: {row[0]} | Count: {row[1]}")
    conn.close()

if __name__ == "__main__":
    check_sources_today()
