"""Extraction Google Ads — Courtage (besoin de 7+ leads)"""
import asyncio, logging, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from scraper.sniper.headless_extract import search_one

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

KEYWORDS = [
    "courtier prêt immobilier Paris", "courtier prêt immobilier Lyon",
    "courtier prêt immobilier Marseille", "courtier prêt immobilier Bordeaux",
    "courtier prêt immobilier Toulouse", "courtier prêt immobilier Lille",
    "courtier prêt immobilier Nice", "courtier prêt immobilier Strasbourg",
    "courtier prêt immobilier Montpellier", "courtier prêt immobilier Rennes",
    "courtier prêt immobilier Nantes", "courtier prêt immobilier Grenoble",
    "courtier prêt immobilier Aix-en-Provence", "courtier prêt immobilier Toulon",
    "simulation crédit immobilier Paris", "simulation crédit immobilier Lyon",
    "simulation crédit immobilier Marseille", "simulation crédit immobilier Bordeaux",
    "courtier en prêt Paris", "courtier en prêt Lyon",
    "courtier en prêt Marseille", "courtier en prêt Nice",
    "meilleur courtier immobilier Paris", "meilleur courtier immobilier Lyon",
    "comparateur courtier immobilier Paris",
]

async def main():
    all_domains = {}
    for i, kw in enumerate(KEYWORDS):
        if len(all_domains) >= 10:
            break
        port = 9600 + i
        logger.info(f"[{i+1}/{len(KEYWORDS)}] {kw} (port {port})...")
        domains = await search_one(kw, port)
        if domains:
            logger.info(f"  -> {', '.join(domains)}")
            for d in domains:
                all_domains.setdefault(d, kw)
        else:
            logger.info(f"  -> 0 annonces")
        await asyncio.sleep(2)

    print(f"\n=== {len(all_domains)} leads ADS courtage trouvés ===")
    for i, (d, kw) in enumerate(all_domains.items(), 1):
        print(f"{i:2d}. {d} ({kw})")

if __name__ == "__main__":
    asyncio.run(main())
