import sqlite3, json, os

db = r'D:\prospection-machine\data\prospection.db'
out = r'D:\prospection-machine\output\agence_leads.json'
conn = sqlite3.connect(db)
cur = conn.cursor()
q = """
SELECT id, nom, email, telephone, site_web, ville, secteur, statut
FROM prospects
WHERE (nom LIKE '%agence%' OR nom LIKE '%Agence%' OR nom LIKE '%web%' OR nom LIKE '%Web%' OR nom LIKE '%digital%' OR nom LIKE '%Digital%'
       OR secteur LIKE '%agence%' OR secteur LIKE '%web%' OR secteur LIKE '%digital%')
ORDER BY id DESC
LIMIT 500
"""
rows = cur.execute(q).fetchall()
cols = [d[0] for d in cur.description]
leads = [dict(zip(cols, r)) for r in rows]
conn.close()

os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, 'w', encoding='utf-8') as f:
    json.dump(leads, f, ensure_ascii=False, indent=2)
print('WROTE', out, 'ROWS', len(leads))
for lead in leads[:20]:
    print(lead['id'], lead.get('nom'), lead.get('site_web'))
