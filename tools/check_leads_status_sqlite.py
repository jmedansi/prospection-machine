import sqlite3, sys, os

# Connect directly to the SQLite file without importing project modules
root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
db_path = os.path.join(root, 'data', 'prospection.db')

if not os.path.exists(db_path):
    print('DB_NOT_FOUND:', db_path)
    sys.exit(2)

ids = [int(x) for x in sys.argv[1:]] if len(sys.argv) > 1 else []
if not ids:
    print('USAGE: python tools/check_leads_status_sqlite.py <id> ...')
    sys.exit(1)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
q = ','.join('?' for _ in ids)
sql = f"SELECT lb.id, lb.nom, lb.statut, la.audit_error, la.lien_rapport, la.template_used FROM leads_bruts lb LEFT JOIN leads_audites la ON la.lead_id=lb.id WHERE lb.id IN ({q})"
rows = conn.execute(sql, ids).fetchall()
for r in rows:
    print(f"{r['id']}\t{r['nom']}\tstatut={r['statut']}\taudit_error={r['audit_error']}\tlien={r['lien_rapport']}\ttpl={r['template_used']}")
conn.close()
