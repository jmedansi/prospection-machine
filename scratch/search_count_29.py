# -*- coding: utf-8 -*-
import sqlite3
import os

def main():
    db_path = 'data/prospection.db'
    if not os.path.exists(db_path):
        db_path = '../data/prospection.db'
        
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    print("=== SEARCHING FOR THE VALUE 29 IN DATABASE STATS ===")
    
    # 1. Check counts of leads_bruts by status
    cur1 = conn.execute("SELECT statut, COUNT(*) as c FROM leads_bruts GROUP BY statut")
    for r in cur1.fetchall():
        if r['c'] == 29:
            print(f"[FOUND] Table leads_bruts has exactly 29 leads with statut='{r['statut']}'")
        else:
            print(f"leads_bruts count for statut='{r['statut']}': {r['c']}")
            
    # 2. Check counts by source
    cur2 = conn.execute("SELECT source, COUNT(*) as c FROM leads_bruts GROUP BY source")
    for r in cur2.fetchall():
        if r['c'] == 29:
            print(f"[FOUND] Table leads_bruts has exactly 29 leads with source='{r['source']}'")
            
    # 3. Check counts of leads_bruts by campaign
    cur3 = conn.execute("SELECT campaign_id, COUNT(*) as c FROM leads_bruts GROUP BY campaign_id")
    for r in cur3.fetchall():
        if r['c'] == 29:
            cur_camp = conn.execute("SELECT nom FROM campagnes WHERE id = ?", (r['campaign_id'],))
            cname = cur_camp.fetchone()
            name = cname['nom'] if cname else 'Unknown'
            print(f"[FOUND] Campaign ID {r['campaign_id']} ('{name}') has exactly 29 leads!")
            
    # 4. Check non_audite filter grouped by campaign
    non_audite_query = f"(la.id IS NULL OR la.audit_error IS NOT NULL OR (la.score_performance = 0 AND la.template_used NOT IN ('maquette', 'reputation') AND lb.statut NOT IN ('audite', 'email_genere', 'envoye', 'repondu')))"
    cur4 = conn.execute(f"""
        SELECT lb.campaign_id, COUNT(*) as c
        FROM leads_bruts lb
        LEFT JOIN leads_audites la ON la.lead_id = lb.id
        WHERE {non_audite_query}
          AND lb.statut NOT IN ('archive', 'desabonne')
        GROUP BY lb.campaign_id
    """)
    for r in cur4.fetchall():
        if r['c'] == 29:
            cur_camp = conn.execute("SELECT nom FROM campagnes WHERE id = ?", (r['campaign_id'],))
            cname = cur_camp.fetchone()
            name = cname['nom'] if cname else 'Unknown'
            print(f"[FOUND] Campaign ID {r['campaign_id']} ('{name}') has exactly 29 NON-AUDITED leads!")

if __name__ == '__main__':
    main()
