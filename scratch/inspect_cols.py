import sqlite3

def inspect_columns():
    db_path = 'data/prospection.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("--- Columns in leads_bruts ---")
    cursor.execute("PRAGMA table_info(leads_bruts)")
    for col in cursor.fetchall():
        print(col[1], end=", ")
    print("\n")
    
    print("--- Columns in leads_audites ---")
    cursor.execute("PRAGMA table_info(leads_audites)")
    for col in cursor.fetchall():
        print(col[1], end=", ")
    print("\n")
    
    conn.close()

if __name__ == "__main__":
    inspect_columns()
