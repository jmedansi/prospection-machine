import sys, os, time, logging
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

from services.sniper_runner import launch_sniper
from database.db_manager import get_conn

ok, msg = launch_sniper(
    keywords=['agence immobiliere', 'agent immobilier', 'acheter appartement',
              'vendre maison', 'estimation immobiliere'],
    country='fr',
    max_per_kw=6,
    pages_per_kw=6,
    parallel_enrich=2,
    campaign_name='Ads-immobilier',
    min_leads=15,
    secteur='immobilier',
)
print(f'Lancement: ok={ok} msg={msg}')

if ok:
    print('Surveillance en cours (poll 30s)...')
    while True:
        c = get_conn().cursor()
        c.execute("SELECT id FROM campagnes WHERE nom='Ads-immobilier' ORDER BY id DESC LIMIT 1")
        row = c.fetchone()
        if row:
            camp_id = row[0]
            c.execute("SELECT phase, total_leads FROM campagnes WHERE id=?", (camp_id,))
            r = c.fetchone()
            c.execute("SELECT COUNT(*) FROM leads_bruts WHERE campaign_id=?", (camp_id,))
            n = c.fetchone()[0]
            print(f'  Campagne #{camp_id}: phase={r[0]} total_leads={r[1]} real_leads={n}')
            if r[0] in ('done', 'failed', 'stopped'):
                print('Termine')
                break
        time.sleep(30)
