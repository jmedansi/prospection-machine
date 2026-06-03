#!/usr/bin/env python3
import sqlite3
from pathlib import Path
from datetime import date
DB = Path(__file__).parent.parent / 'data' / 'prospection.db'
conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row
today = date.today().isoformat()
rows = conn.execute('''
    SELECT la.id, la.lead_id, lb.nom, la.statut, la.template_used, la.lien_rapport, la.date_audit
    FROM leads_audites la
    LEFT JOIN leads_bruts lb ON la.lead_id = lb.id
    WHERE date(la.date_audit) = ?
    ORDER BY la.id DESC
''', (today,)).fetchall()
print(f"Audits pour {today} : {len(rows)} lignes")
for r in rows:
    print(f"{r['id']} {r['lead_id']} {r['nom']} {r['statut']} {r['template_used']} {(r['lien_rapport'] or '-')} {r['date_audit']}")
