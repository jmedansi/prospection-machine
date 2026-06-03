# -*- coding: utf-8 -*-
import sys
import os

# Add project root to sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from database.repos import leads_repo

def main():
    print("=== TESTING LEADS REPO COUNT FOR NON-AUDITED ADS LEADS ===")
    res = leads_repo.get_all(statut='non_audite', source='ads')
    print(f"Total returned by get_all: {res['total']}")
    
    print("\nLeads returned:")
    for lead in res['leads']:
        print(f"ID: {lead['id']} | Nom: {lead['nom'][:30]} | Site: {lead['site_web']} | Statut: {lead['statut']}")

if __name__ == '__main__':
    main()
