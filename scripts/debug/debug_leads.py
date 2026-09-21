#!/usr/bin/env python3
import sys, os
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from database.connection import get_conn
from database.repos.leads_repo import LeadsRepo
import json

# Verifier combien de leads existent par source
with get_conn() as conn:
    sources = conn.execute("SELECT source, COUNT(*) as cnt FROM leads_bruts GROUP BY source").fetchall()
    print("Leads par source:")
    for s in sources:
        print(f"  {s['source']}: {s['cnt']}")

print("\n---\n")

# Verifier les 10 derniers leads 'ads'
repo = LeadsRepo()
result = repo.get_all(source='ads', statut='tous', limit=10)
leads = result.get('items', [])
print(f"Leads trouves avec source='ads': {len(leads)}")
if leads:
    print(json.dumps([{'id': l['id'], 'nom': l['nom'], 'site_web': l['site_web'][:50]} for l in leads[:3]], indent=2, ensure_ascii=False))

print("\n---\n")

# Si 0, essayer sans filtre source
result_all = repo.get_all(statut='tous', limit=10)
leads_all = result_all.get('items', [])
print(f"Leads trouves SANS filtre source: {len(leads_all)}")
if leads_all:
    print("Premiers 3:")
    for l in leads_all[:3]:
        print(f"  ID {l['id']}: {l['nom']} - source={l.get('source')}")
