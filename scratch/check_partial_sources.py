import sqlite3

def check_partial_sources():
    db_path = 'data/prospection.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("--- Sources of leads with audit_partial = 1 ---")
    cursor.execute("""
        SELECT lb.source, COUNT(*) 
        FROM leads_bruts lb
        JOIN leads_audites la ON lb.id = la.lead_id
        WHERE la.audit_partial = 1
        GROUP BY lb.source
    """)
    for row in cursor.fetchall():
        print(row)
        
    print("\n--- Details of some partial Google Ads leads ---")
    cursor.execute("""
        SELECT lb.id, lb.nom, lb.site_web, la.mobile_score, la.pagespeed_error
        FROM leads_bruts lb
        JOIN leads_audites la ON lb.id = la.lead_id
        WHERE la.audit_partial = 1 AND lb.source LIKE '%ads%'
        LIMIT 10
    """)
    for row in cursor.fetchall():
        print(row)
    
    conn.close()

if __name__ == "__main__":
    check_partial_sources()
