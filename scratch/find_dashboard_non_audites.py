# -*- coding: utf-8 -*-
import sqlite3
import os

def main():
    db_path = 'data/prospection.db'
    if not os.path.exists(db_path):
        db_path = '../data/prospection.db'
        
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    # Dashboard query for 'non_audite'
    is_audit_valid = "(la.id IS NOT NULL AND la.audit_error IS NULL AND (la.score_performance > 0 OR la.template_used IN ('maquette', 'reputation') OR lb.statut IN ('audite', 'email_genere', 'envoye', 'repondu')))"
    non_audite_query = f"(la.id IS NULL OR la.audit_error IS NOT NULL OR (la.score_performance = 0 AND la.template_used NOT IN ('maquette', 'reputation') AND lb.statut NOT IN ('audite', 'email_genere', 'envoye', 'repondu')))"
    
    # 1. Total counts by source for 'non_audite'
    cur = conn.execute(f"""
        SELECT 
            CASE 
                WHEN lb.source IN ('ads', 'fb_ads', 'transparency', 'tech', 'ecom', 'jobs', 'bodacc') THEN 'sniper'
                ELSE 'maps'
            END AS pipeline,
            lb.source,
            COUNT(*) as count
        FROM leads_bruts lb
        LEFT JOIN leads_audites la ON la.lead_id = lb.id
        WHERE {non_audite_query}
          AND lb.statut NOT IN ('archive', 'desabonne')
        GROUP BY pipeline, lb.source
    """)
    print("=== NON-AUDITED LEADS ON DASHBOARD BY SOURCE ===")
    for r in cur.fetchall():
        print(f"Pipeline: {r['pipeline']:<10} | Source: {r['source']:<15} | Count: {r['count']}")

    # 2. Let's see some examples if there are any sniper ones
    cur_ex = conn.execute(f"""
        SELECT lb.id, lb.nom, lb.site_web, lb.source, lb.statut
        FROM leads_bruts lb
        LEFT JOIN leads_audites la ON la.lead_id = lb.id
        WHERE {non_audite_query}
          AND lb.statut NOT IN ('archive', 'desabonne')
          AND lb.source = 'ads'
        LIMIT 10
    """)
    rows_ex = cur_ex.fetchall()
    if rows_ex:
        print("\n=== EXAMPLES OF NON-AUDITED GOOGLE ADS LEADS ===")
        for r in rows_ex:
            print(f"ID: {r['id']} | Nom: {r['nom'][:30]:<30} | Site: {r['site_web']} | Source: {r['source']} | Statut: {r['statut']}")
    else:
        print("\nNo pending/non-audited Google Ads leads found.")

if __name__ == '__main__':
    main()
