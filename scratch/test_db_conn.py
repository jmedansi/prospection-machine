# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.connection import DB_PATH, get_conn

def main():
    print(f"DB_PATH defined in connection.py: {DB_PATH}")
    print(f"Absolute DB_PATH: {DB_PATH.resolve()}")
    print(f"File exists: {DB_PATH.exists()}")
    print(f"File size: {os.path.getsize(str(DB_PATH)) if DB_PATH.exists() else 'N/A'} bytes")
    
    try:
        with get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM leads_bruts")
            count = c.fetchone()[0]
            print(f"Direct count via get_conn() on leads_bruts: {count}")
    except Exception as e:
        print(f"Error executing count: {e}")

if __name__ == "__main__":
    main()
