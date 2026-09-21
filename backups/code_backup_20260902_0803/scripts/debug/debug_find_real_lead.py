import sqlite3
from pathlib import Path

DB = Path('data/prospection.db')
if not DB.exists():
    raise SystemExit(f'DB not found: {DB}')

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.execute(
    """
    SELECT lb.id AS lead_id, lb.nom, lb.email, lb.site_web, lb.telephone,
           la.approuve, la.email_objet IS NOT NULL AS has_objet,
           la.email_corps IS NOT NULL AS has_corps, la.lien_rapport
    FROM leads_bruts lb
    JOIN leads_audites la ON la.lead_id = lb.id
    WHERE la.approuve = 1
      AND lb.email IS NOT NULL
      AND lb.email != ''
    ORDER BY lb.id DESC
    LIMIT 20
    """
)
rows = cur.fetchall()
print('count', len(rows))
for r in rows:
    print({k: r[k] for k in r.keys()})
conn.close()
