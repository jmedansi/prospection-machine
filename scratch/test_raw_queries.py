# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.connection import get_conn

def main():
    with get_conn() as conn:
        c = conn.cursor()
        
        # 1. Simple count on leads_bruts
        c.execute("SELECT COUNT(*) FROM leads_bruts")
        print(f"leads_bruts count: {c.fetchone()[0]}")
        
        # 2. Count with LEFT JOIN on leads_audites
        try:
            c.execute("SELECT COUNT(*) FROM leads_bruts lb LEFT JOIN leads_audites la ON la.lead_id = lb.id")
            print(f"LEFT JOIN count: {c.fetchone()[0]}")
        except Exception as e:
            print(f"Error in LEFT JOIN: {e}")
            
        # 3. Let's fetch one row from leads_bruts
        c.execute("SELECT * FROM leads_bruts LIMIT 1")
        row = c.fetchone()
        if row:
            print(f"Sample lead: {dict(row)}")
        else:
            print("No leads in leads_bruts")
            
        # 4. Let's see leads_audites count
        c.execute("SELECT COUNT(*) FROM leads_audites")
        print(f"leads_audites count: {c.fetchone()[0]}")

if __name__ == "__main__":
    main()
