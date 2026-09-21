import sqlite3
import json
from pathlib import Path

output_path = Path('ml_raw_text_rows.jsonl')
readable_path = Path('ml_raw_text_rows_readable.txt')
conn = sqlite3.connect('data/prospection.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()
rows = c.execute("SELECT id, nom, site_web, ml_extracted FROM leads_bruts WHERE json_extract(ml_extracted, '$.raw_text') IS NOT NULL").fetchall()
print('total raw_text rows', len(rows))
lines = []
readable = []
for row in rows:
    try:
        data = json.loads(row['ml_extracted'])
        raw_text = data.get('raw_text')
        if raw_text:
            lines.append(json.dumps({'id': row['id'], 'nom': row['nom'], 'site_web': row['site_web'], 'raw_text': raw_text}, ensure_ascii=False))
            readable.append(f"ID: {row['id']}\nNOM: {row['nom']}\nSITE: {row['site_web']}\n---\n{raw_text[:2000].replace('\n',' ')}\n\n{'='*80}\n")
    except Exception:
        pass
output_path.write_text('\n'.join(lines), encoding='utf-8')
readable_path.write_text('\n'.join(readable), encoding='utf-8')
print(f'Wrote {len(lines)} entries to {output_path}')
print(f'Wrote readable dump to {readable_path}')
