import sqlite3
import os

def check_statuses():
    db_path = 'data/prospection.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("--- Status counts in leads_bruts ---")
    cursor.execute("SELECT statut, COUNT(*) FROM leads_bruts GROUP BY statut")
    for row in cursor.fetchall():
        print(row)
        
    print("\n--- Status counts in leads_audites ---")
    # check if leads_audites has a status column (sometimes called statut_prospection)
    cursor.execute("PRAGMA table_info(leads_audites)")
    cols = [c[1] for c in cursor.fetchall()]
    if 'statut' in cols:
        cursor.execute("SELECT statut, COUNT(*) FROM leads_audites GROUP BY statut")
        for row in cursor.fetchall():
            print(row)
    elif 'statut_prospection' in cols:
        cursor.execute("SELECT statut_prospection, COUNT(*) FROM leads_audites GROUP BY statut_prospection")
        for row in cursor.fetchall():
            print(row)
    
    conn.close()

if __name__ == "__main__":
    check_statuses()
