# -*- coding: utf-8 -*-
import sqlite3
import os

def main():
    db_path = 'data/prospection.db'
    if not os.path.exists(db_path):
        db_path = '../data/prospection.db'
        
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    non_audite_query = f"(la.id IS NULL OR la.audit_error IS NOT NULL OR (la.score_performance = 0 AND la.template_used NOT IN ('maquette', 'reputation') AND lb.statut NOT IN ('audite', 'email_genere', 'envoye', 'repondu')))"
    
    # Count by campaign for 'non_audite'
    cur = conn.execute(f"""
        SELECT lb.campaign_id, c.nom as campaign_name, lb.source, COUNT(*) as count
        FROM leads_bruts lb
        LEFT JOIN leads_audites la ON la.lead_id = lb.id
        LEFT JOIN campagnes c ON c.id = lb.campaign_id
        WHERE {non_audite_query}
          AND lb.statut NOT IN ('archive', 'desabonne')
        GROUP BY lb.campaign_id, lb.source
    """)
    print("=== NON-AUDITED LEADS BY CAMPAIGN AND SOURCE ===")
    for r in cur.fetchall():
        name = r['campaign_name'] or 'No Campaign'
        cid_str = str(r['campaign_id']) if r['campaign_id'] is not None else 'None'
        print(f"Campaign ID: {cid_str:<6} | Name: {name:<35} | Source: {r['source']:<10} | Count: {r['count']}")

if __name__ == '__main__':
    main()
