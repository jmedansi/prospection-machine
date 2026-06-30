from database.connection import get_conn
from agents.enrichisseur.agent import enrichisseur_agent
import time


def main():
    conn = get_conn()
    rows = conn.execute(
        "SELECT id FROM leads_bruts WHERE site_web IS NOT NULL AND site_web != '' AND COALESCE(email_valide, '') = ''"
    ).fetchall()
    lead_ids = [r[0] for r in rows]
    total = len(lead_ids)
    print("Lead count to enrich:", total)
    if not lead_ids:
        print("Aucun lead trouvé pour enrichissement.")
        return

    success = 0
    failed = 0
    results = []
    for i, lid in enumerate(lead_ids, start=1):
        res = enrichisseur_agent._enrich_single(lid)
        if res.success and res.data.get('enriched_fields'):
            success += 1
            results.append({'id': lid, 'status': 'success', 'found': list(res.data['enriched_fields'].keys())})
        elif res.success:
            failed += 1
            results.append({'id': lid, 'status': 'no_new_data'})
        else:
            failed += 1
            results.append({'id': lid, 'status': 'error', 'error': res.error})
        if i % 10 == 0 or i == total:
            print(f"Progress: {i}/{total} — success={success} failed={failed}")

    print('Done')
    print('Total:', total)
    print('Success:', success)
    print('Failed:', failed)
    print('Results stored:', len(results))


if __name__ == '__main__':
    main()
