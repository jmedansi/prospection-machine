
import sqlite3
import os

db_path = "data/prospection.db"

def check_lead(lid):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM leads_bruts WHERE id = ?", (lid,)).fetchone()
    if row:
        print(dict(row))
    else:
        print("Not found")
    conn.close()

if __name__ == "__main__":
    check_lead(1720)
