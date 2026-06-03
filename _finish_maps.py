import sys, os, time, logging
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from services.scraper_runner import launch_scraper
from database.db_manager import get_conn

logging.basicConfig(
    level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('data/logs/finish_maps.log', encoding='utf-8'),
    ]
)
logger = logging.getLogger('finish_maps')

CITIES = [
    "Lyon", "Marseille", "Bordeaux", "Toulouse", "Lille",
    "Nice", "Nantes", "Strasbourg", "Montpellier", "Rennes",
    "Rouen", "Toulon", "Grenoble", "Dijon", "Angers",
    "Nimes", "Aix-en-Provence", "Saint-Etienne", "Tours", "Reims",
    "Clermont-Ferrand", "Orleans", "Le Havre", "Brest", "Metz",
    "Perpignan", "Besancon", "Limoges", "Caen",
]

SECTORS = [
    ("cliniques_esthetiques", ["clinique esthétique", "médecine esthétique", "centre esthétique"]),
    ("concessionnaires_auto", ["concessionnaire automobile", "concession auto", "garage automobile"]),
    ("ecoles_formation", ["centre de formation", "organisme de formation", "école de formation"]),
]

def count_leads(sector):
    c = get_conn().cursor()
    c.execute("SELECT COUNT(*) FROM leads_bruts WHERE secteur=? AND source='maps' AND nb_avis>=50", (sector,))
    return c.fetchone()[0]

for sector, keywords in SECTORS:
    logger.info(f"{'='*60}")
    logger.info(f"SECTEUR: {sector}")
    initial = count_leads(sector)
    logger.info(f"  Départ: {initial}/20")

    for keyword in keywords:
        current = count_leads(sector)
        if current >= 20:
            logger.info(f"  Quota atteint {current}/20")
            break
        logger.info(f"  Keyword: {keyword} — besoin de {20-current} leads")

        for city in CITIES:
            current = count_leads(sector)
            if current >= 20:
                logger.info(f"  Quota atteint {current}/20!")
                break

            limit = 30
            logger.info(f"  → Lancement {keyword} @ {city}")
            ok, camp_id = launch_scraper(
                keyword=keyword, city=city, sector=sector, limit=limit,
                min_emails=0, campaign_name=f"Maps-{sector}-{keyword}-{city}",
                min_reviews=0, multi_zone=False)
            if ok:
                logger.info(f"    #{camp_id}: {keyword} @ {city}")
                deadline = time.time() + 3600
                while time.time() < deadline:
                    c = get_conn().cursor()
                    c.execute("SELECT phase FROM campagnes WHERE id=?", (camp_id,))
                    r = c.fetchone()
                    if r and r[0] in ('done', 'failed', 'stopped'):
                        break
                    time.sleep(15)

                after = count_leads(sector)
                logger.info(f"    -> {after}/20 pour {sector}")
                if after - current > 0:
                    logger.info(f"    ✓ +{after - current} nouveaux leads avec 50+ avis")
            else:
                logger.error(f"    ✗ Échec {keyword} @ {city}: {camp_id}")

    final = count_leads(sector)
    logger.info(f"  Résultat {sector}: {final}/20")

logger.info("TERMINÉ")
for sector, _ in SECTORS:
    logger.info(f"  {sector}: {count_leads(sector)}/20")
