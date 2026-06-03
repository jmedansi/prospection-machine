import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.connection import get_conn

def main():
    ids = [int(x) for x in sys.argv[1:]] if len(sys.argv) > 1 else []
    if not ids:
        print("USAGE: python tools/check_leads_status.py <id> ...")
        return
    q = ",".join("?" for _ in ids)
    sql = f"SELECT lb.id, lb.nom, lb.statut, la.mobile_performance_error, la.lien_rapport, la.template_used FROM leads_bruts lb LEFT JOIN leads_audites la ON la.lead_id=lb.id WHERE lb.id IN ({q})"
    with get_conn() as conn:
        rows = conn.execute(sql, ids).fetchall()
        for r in rows:
            print(f"{r['id']}\t{r['nom']}\tstatut={r['statut']}\tperf_err={r['mobile_performance_error']}\tlien={r['lien_rapport']}\ttpl={r['template_used']}")

if __name__ == "__main__":
    main()
