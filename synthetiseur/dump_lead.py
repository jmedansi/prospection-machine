import sqlite3
from pathlib import Path

DB = Path(__file__).parent.parent / 'data' / 'prospection.db'

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print('Usage: python dump_lead.py <id>')
        sys.exit(1)
    lead_id = int(sys.argv[1])
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('SELECT * FROM leads_bruts WHERE id = ?', (lead_id,))
    row = cur.fetchone()
    if not row:
        print('NO ROW', lead_id)
        sys.exit(1)
    print('COLUMNS:', list(row.keys()))
    for k in row.keys():
        print(k, repr(row[k]))
    conn.close()
