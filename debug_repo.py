#!/usr/bin/env python3
import sys, os
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from database.connection import get_conn

# Vérifier les leads ads
conn = get_conn()
rows = conn.execute('SELECT COUNT(*) FROM leads_bruts WHERE source = ?', ('ads',)).fetchall()
print(f'Leads source=ads (exact): {rows[0][0]}')

rows2 = conn.execute('SELECT id, nom, source, statut FROM leads_bruts WHERE source = ? LIMIT 5', ('ads',)).fetchall()
print('Sample leads ads:')
for r in rows2:
    print(f'  ID {r[0]}: {r[1]} - source={r[2]}, statut={r[3]}')

# Vérifier la query que get_all() construit
print('\n---\n')

# Now try with LeadsRepo methods directly
from database.repos.leads_repo import LeadsRepo
repo = LeadsRepo()

# Try raw query
print('Trying raw SQL:')
all_rows = conn.execute("""
    SELECT lb.id, lb.nom, lb.source, lb.statut
    FROM leads_bruts lb
    WHERE lb.source = 'ads'
    ORDER BY lb.id DESC
    LIMIT 10
""").fetchall()
print(f'Raw SQL result: {len(all_rows)} rows')
for r in all_rows[:3]:
    print(f'  {r[0]}: {r[1]} - {r[2]}')

print('\n---\n')

# Now let's understand the _build_filters method
print('Checking repo._build_filters...')
where, params = repo._build_filters(statut='tous', site='tous', email='tous', sector='tous', search='', campaign_id=None, campaign_ids=None, date_start=None, date_end=None, source='ads', tag='', score='tous', notes='tous')
print(f'WHERE clause: {where}')
print(f'Params: {params}')

# Now let's try executing the actual query the repo builds
base_query = """
    SELECT
        lb.*,
        la.id AS audit_id,
        la.mobile_score, la.mobile_score AS score_mobile,
        la.score_urgence,
        la.score_performance AS score_perf,
        la.score_seo,
        la.email_objet, la.email_corps, la.approuve,
        la.lien_rapport, la.lien_pdf,
        la.probleme_principal, la.service_suggere,
        la.statut_prospection,
        COALESCE(NULLIF(la.email_valide, ''), NULLIF(lb.email_valide, '')) AS email_valide,
        la.audit_partial,
        la.ceo_prenom, la.ceo_nom, la.ceo_source
    FROM leads_bruts lb
    LEFT JOIN leads_audites la ON la.lead_id = lb.id
"""

full_query = f"{base_query} {where} ORDER BY lb.id DESC LIMIT 10 OFFSET 0"
print(f'\nFull query: {full_query}')
print(f'With params: {params}')

rows3 = conn.execute(full_query, params).fetchall()
print(f'\nFull query result: {len(rows3)} rows')
