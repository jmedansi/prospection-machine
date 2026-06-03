# -*- coding: utf-8 -*-
import sys
import os
import time

# Add root folder to sys.path to allow imports
sys.path.append(os.path.abspath('.'))

from database.connection import get_conn
from database.repos.leads_repo import leads_repo

def main():
    print("=== EXPLAINING EXACT GET_ALL QUERY PLAN ===")
    
    # Simulate the leads_repo.get_all call
    start_time = time.time()
    res = leads_repo.get_all(statut="tous", limit=50, page=1)
    elapsed = time.time() - start_time
    print(f"leads_repo.get_all completed in {elapsed:.3f} seconds.")
    print(f"Total leads: {res['total']}")
    print(f"Returned leads: {len(res['leads'])}")
    
    # Now let's trace the exact SQL executed behind get_all
    # Let's rebuild the filters using the internal helper _build_filters
    where, params = leads_repo._build_filters(
        statut="tous", site="tous", email="tous", sector="tous", search="",
        campaign_id=None, campaign_ids=None, date_start=None, date_end=None,
        source="tous", tag="", score="tous"
    )
    
    print(f"\nGenerated WHERE clause: {where}")
    print(f"Generated PARAMS: {params}")
    
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
    
    count_query = f"SELECT COUNT(*) FROM leads_bruts lb LEFT JOIN leads_audites la ON la.lead_id = lb.id {where}"
    rows_query = f"{base_query} {where} ORDER BY lb.id DESC LIMIT ? OFFSET ?"
    
    with get_conn() as conn:
        print("\n--- EXPLAIN QUERY PLAN FOR COUNT QUERY ---")
        try:
            plan = conn.execute(f"EXPLAIN QUERY PLAN {count_query}", params).fetchall()
            for step in plan:
                print(dict(step))
        except Exception as e:
            print(f"Explain count failed: {e}")
            
        print("\n--- EXPLAIN QUERY PLAN FOR ROWS QUERY ---")
        try:
            # For explain, we append placeholder limit/offset
            plan = conn.execute(f"EXPLAIN QUERY PLAN {rows_query}", params + [50, 0]).fetchall()
            for step in plan:
                print(dict(step))
        except Exception as e:
            print(f"Explain rows failed: {e}")
            
        # Time the count query
        t0 = time.time()
        c = conn.execute(count_query, params).fetchone()[0]
        t_count = time.time() - t0
        print(f"\nCount query time: {t_count:.3f} seconds (returned {c})")
        
        # Time the rows query
        t0 = time.time()
        r = conn.execute(rows_query, params + [50, 0]).fetchall()
        t_rows = time.time() - t0
        print(f"Rows query time:  {t_rows:.3f} seconds (returned {len(r)})")

if __name__ == '__main__':
    main()
