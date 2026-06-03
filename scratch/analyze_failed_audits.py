import sqlite3
import os

def analyze_failed_audits():
    db_path = 'data/prospection.db'
    if not os.path.exists(db_path):
        print(f"[!] {db_path} introuvable")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("--- Analyse des leads avec statut 'audit_echoue' ---")
    
    # On cherche dans leads_bruts les leads en échec
    cursor.execute("""
        SELECT lb.id, lb.nom, lb.site_web, lb.source, la.pagespeed_error, la.http_error, la.audit_error, la.audit_partial
        FROM leads_bruts lb
        LEFT JOIN leads_audites la ON lb.id = la.lead_id
        WHERE lb.statut = 'audit_echoue'
        LIMIT 20
    """)
    
    rows = cursor.fetchall()
    if not rows:
        print("Aucun lead trouvé avec le statut 'audit_echoue'.")
    else:
        for row in rows:
            print(f"\nID: {row['id']} | Nom: {row['nom']}")
            print(f"  URL: {row['site_web']} | Source: {row['source']}")
            print(f"  PageSpeed Err: {row['pagespeed_error']} | HTTP Err: {row['http_error']} | Audit Err: {row['audit_error']}")
            print(f"  Partial: {row['audit_partial']}")

    conn.close()

if __name__ == "__main__":
    analyze_failed_audits()
