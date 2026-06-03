import sqlite3, sys, os, time
root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
db_path = os.path.join(root, 'data', 'prospection.db')
ids = [int(x) for x in sys.argv[1:]] if len(sys.argv) > 1 else []
if not ids:
    print('USAGE: python tools/wait_for_leads_processed.py <id> ...')
    sys.exit(1)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
q = ','.join('?' for _ in ids)
max_wait = 120
interval = 3
start = time.time()

while True:
    rows = conn.execute(f"SELECT id, nom, statut FROM leads_bruts WHERE id IN ({q})", ids).fetchall()
    still = [r for r in rows if r['statut']=='en_attente']
    print('STATUS:', '; '.join(f"{r['id']}={r['statut']}" for r in rows))
    if not still:
        print('ALL_PROCESSED')
        break
    if time.time() - start > max_wait:
        print('TIMEOUT')
        break
    time.sleep(interval)

conn.close()
