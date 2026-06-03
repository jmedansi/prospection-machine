#!/usr/bin/env python3
import sqlite3
from pathlib import Path
DB = Path(__file__).parent.parent / 'data' / 'prospection.db'
conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row
rows = conn.execute('''
    SELECT la.id, la.lead_id, lb.nom, la.statut, la.template_used, la.lien_rapport, la.date_audit
    FROM leads_audites la
    LEFT JOIN leads_bruts lb ON la.lead_id = lb.id
    ORDER BY la.id DESC
    LIMIT 60
''').fetchall()
for r in rows:
    print(f"{r['id']} {r['lead_id']} {r['nom']} {r['statut']} {r['template_used']} {(r['lien_rapport'] or '-')} {r['date_audit']}")
