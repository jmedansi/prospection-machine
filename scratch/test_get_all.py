# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.repos.leads_repo import leads_repo

def main():
    print("Testing LeadsRepo.get_all()...")
    
    # Test with default values
    res = leads_repo.get_all(
        statut="tous",
        limit=50,
        page=1,
        site="tous",
        email="tous",
        sector="tous",
        search="",
        campaign_id=None,
        campaign_ids=None,
        date_start=None,
        date_end=None,
        source="tous",
        tag="",
        score="tous"
    )
    print(f"Result with all 'tous': total={res['total']}, leads_count={len(res['leads'])}")
    
    # Let's inspect where and params generated
    where, params = leads_repo._build_filters(
        statut="tous",
        site="tous",
        email="tous",
        sector="tous",
        search="",
        campaign_id=None,
        campaign_ids=None,
        date_start=None,
        date_end=None,
        source="tous",
        tag="",
        score="tous"
    )
    print(f"Generated WHERE: '{where}'")
    print(f"Generated PARAMS: {params}")

if __name__ == "__main__":
    main()
