import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from services.scraper_runner import launch_scraper
from database.db_manager import get_conn

CITIES = ["Lyon", "Marseille", "Bordeaux", "Toulouse", "Lille",
    "Nice", "Nantes", "Strasbourg", "Montpellier", "Rennes", "Rouen",
    "Toulon", "Grenoble", "Dijon", "Angers", "Aix-en-Provence",
    "Saint-Etienne", "Tours", "Reims", "Clermont-Ferrand"]

KEYWORDS = ["clinique esthetique", "medecine esthetique", "centre esthetique"]
SECTOR = "cliniques_esthetiques"

def count_leads():
    c = get_conn().cursor()
    c.execute("SELECT COUNT(*) FROM leads_bruts WHERE secteur=? AND source='maps' AND nb_avis>=50", (SECTOR,))
    return c.fetchone()[0]

for keyword in KEYWORDS:
    current = count_leads()
    if current >= 20:
        print(f"Quota atteint pour {SECTOR} ({current}/20)")
        break

    for city in CITIES:
        current = count_leads()
        if current >= 20:
            print(f"Quota atteint ! ({current}/20)")
            break

        ok, camp_id = launch_scraper(
            keyword=keyword, city=city, sector=SECTOR,
            limit=30, min_emails=0,
            campaign_name=f"Maps-{SECTOR}-{keyword}-{city}",
            min_reviews=0, multi_zone=False,
        )
        if ok:
            print(f"#{camp_id}: {keyword} @ {city}")
            deadline = time.time() + 600
            while time.time() < deadline:
                c = get_conn().cursor()
                c.execute("SELECT phase FROM campagnes WHERE id=?", (camp_id,))
                r = c.fetchone()
                if r and r[0] in ('done','failed','stopped'):
                    break
                time.sleep(15)
            print(f"  -> Fini: {count_leads()}/20")

print(f"Final: {count_leads()}/20")
