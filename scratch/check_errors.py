import sqlite3

def check_errors():
    db_path = 'data/prospection.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("--- Leads with audit_error ---")
    cursor.execute("SELECT lead_id, audit_error, pagespeed_error, http_error FROM leads_audites WHERE audit_error != 0 AND audit_error IS NOT NULL")
    for row in cursor.fetchall():
        print(row)
        
    print("\n--- Leads with audit_partial = 1 ---")
    cursor.execute("SELECT lead_id, audit_error, pagespeed_error, http_error FROM leads_audites WHERE audit_partial = 1")
    for row in cursor.fetchall():
        print(row)

    print("\n--- Leads with statut = 'audit_echoue' in leads_bruts ---")
    cursor.execute("SELECT id, nom, site_web FROM leads_bruts WHERE statut = 'audit_echoue'")
    for row in cursor.fetchall():
        print(row)
    
    conn.close()

if __name__ == "__main__":
    check_errors()
