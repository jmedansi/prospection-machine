from database.connection import get_conn
from agents.enrichisseur.agent import enrichisseur_agent


def main():
    conn = get_conn()
    rows = conn.execute(
        "SELECT id FROM leads_bruts WHERE site_web IS NOT NULL AND site_web != '' AND COALESCE(email_valide, '') = ''"
    ).fetchall()
    lead_ids = [r[0] for r in rows]
    print("Lead count to enrich:", len(lead_ids))
    if not lead_ids:
        print("Aucun lead trouvé pour enrichissement.")
        return
    result = enrichisseur_agent.run(lead_ids=lead_ids)
    print("Result success:", result.success)
    print("Result error:", result.error)
    print("Result data:", result.data)


if __name__ == '__main__':
    main()
