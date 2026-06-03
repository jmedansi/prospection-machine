import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT)

from database.connection import get_conn
from auditeur.main import run_tech_audit_sqlite

def main():
    print("=== RUNNING REAL AUDIT TEST ===")
    
    # 1. Find a pending lead with a real website (not doctolib, not facebook, etc.)
    with get_conn() as conn:
        row = conn.execute("""
            SELECT id, nom, site_web, statut FROM leads_bruts
            WHERE statut = 'en_attente'
              AND site_web LIKE 'http%'
              AND site_web NOT LIKE '%doctolib.fr%'
              AND site_web NOT LIKE '%facebook.com%'
              AND site_web NOT LIKE '%instagram.com%'
              AND site_web NOT LIKE '%google.com%'
            LIMIT 1
        """).fetchone()
        
    if not row:
        print("No suitable pending lead found with a real website. Checking any pending lead with a website...")
        with get_conn() as conn:
            row = conn.execute("""
                SELECT id, nom, site_web, statut FROM leads_bruts
                WHERE statut = 'en_attente'
                  AND site_web LIKE 'http%'
                LIMIT 1
            """).fetchone()
            
    if not row:
        print("No pending lead with a website found.")
        return
        
    lead_id = row['id']
    nom = row['nom']
    site_web = row['site_web']
    print(f"Found Lead: ID {lead_id} | Name: {nom} | Website: {site_web}")
    
    # 2. Run the audit
    print("\nStarting orchestrator audit...")
    run_tech_audit_sqlite(lead_ids=[lead_id])
    
    # 3. Check the results in the DB
    print("\nChecking audit results in database...")
    with get_conn() as conn:
        lead_row = conn.execute("SELECT statut FROM leads_bruts WHERE id = ?", (lead_id,)).fetchone()
        audit_row = conn.execute("SELECT * FROM leads_audites WHERE lead_id = ?", (lead_id,)).fetchone()
        
        print(f"Lead status: {lead_row['statut']}")
        if audit_row:
            print("Audit row data:")
            for k, v in dict(audit_row).items():
                if k not in ('email_corps', 'email_objet'):
                    print(f"  {k}: {v}")
                else:
                    print(f"  {k}: (Length={len(v) if v else 0})")
        else:
            print("No audit row created in database!")

if __name__ == '__main__':
    main()
