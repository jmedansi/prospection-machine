import sqlite3
import json
import csv
import os

DB = r'D:\prospection-machine\data\prospection.db'
IN = r'D:\prospection-machine\output\agence_leads.json'
OUT_JSON = r'D:\prospection-machine\output\agence_leads_full.json'
OUT_CSV = r'D:\prospection-machine\output\agence_leads_full.csv'

with open(IN, 'r', encoding='utf-8') as f:
    leads = json.load(f)

ids = [l['id'] for l in leads if 'id' in l]

conn = sqlite3.connect(DB)
cur = conn.cursor()

# fetch prospects table columns
cols = [c[1] for c in cur.execute("PRAGMA table_info(prospects)").fetchall()]

results = []
for _id in ids:
    row = cur.execute('SELECT * FROM prospects WHERE id=?', (_id,)).fetchone()
    if not row:
        continue
    obj = dict(zip(cols, row))
    results.append(obj)

conn.close()

os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
with open(OUT_JSON, 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

# write CSV, flatten JSON-like fields as strings
all_keys = set()
for r in results:
    all_keys.update(r.keys())
all_keys = list(all_keys)

with open(OUT_CSV, 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction='ignore')
    writer.writeheader()
    for r in results:
        row = {}
        for k in all_keys:
            v = r.get(k, '')
            if isinstance(v, (dict, list)):
                row[k] = json.dumps(v, ensure_ascii=False)
            else:
                row[k] = v
        writer.writerow(row)

print('WROTE', OUT_JSON, 'and', OUT_CSV, 'ROWS', len(results))
