#!/usr/bin/env python
from database.connection import get_conn

with get_conn() as conn:
    rows = conn.execute('''
        SELECT la.id, la.lead_id, lb.nom, la.statut, la.template_used, la.lien_rapport, la.date_audit
        FROM leads_audites la
        LEFT JOIN leads_bruts lb ON la.lead_id = lb.id
        ORDER BY la.id DESC
        LIMIT 40
    ''').fetchall()
    for r in rows:
        print(r['id'], r['lead_id'], r['nom'], r['statut'], r['template_used'], r['lien_rapport'] or '-', r['date_audit'])
