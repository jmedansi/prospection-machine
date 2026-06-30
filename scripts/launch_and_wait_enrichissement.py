from database.connection import get_conn
from agents.enrichisseur.agent import enrichisseur_agent
import time
import sys


def main(poll_interval=2):
    conn = get_conn()
    rows = conn.execute(
        "SELECT id FROM leads_bruts WHERE site_web IS NOT NULL AND site_web != '' AND COALESCE(email_valide, '') = ''"
    ).fetchall()
    lead_ids = [r[0] for r in rows]
    print("Lead count to enrich:", len(lead_ids))
    if not lead_ids:
        print("Aucun lead trouvé pour enrichissement.")
        return

    res = enrichisseur_agent.run(lead_ids=lead_ids)
    if not res.success:
        print("Erreur lancement:", res.error)
        return

    print("Recherche lancée, total:", res.data.get('total', len(lead_ids)))

    # Poll status until finished
    try:
        while True:
            status = enrichisseur_agent.status()
            print(status)
            if not status.get('running'):
                break
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        print('Interrompu par l\'utilisateur, arrêt du job...')
        enrichisseur_agent.stop()
        sys.exit(1)

    final = enrichisseur_agent.status()
    print('Final status:', final)
    # Summarize
    print('Total:', final.get('total'))
    print('Success:', final.get('success'))
    print('Failed:', final.get('failed'))
    print('Results stored:', len(final.get('results', [])))


if __name__ == '__main__':
    main()
