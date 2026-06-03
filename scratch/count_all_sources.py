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
    
    # Let's count by exact source for non-audited leads
    cur = conn.execute(f"""
        SELECT lb.source, COUNT(*) as count
        FROM leads_bruts lb
        LEFT JOIN leads_audites la ON la.lead_id = lb.id
        WHERE {non_audite_query}
          AND lb.statut NOT IN ('archive', 'desabonne')
        GROUP BY lb.source
    """)
    print("=== NON-AUDITED LEADS BY EXACT SOURCE ===")
    for r in cur.fetchall():
        print(f"Source: {r['source']:<15} | Count: {r['count']}")

if __name__ == '__main__':
    main()
