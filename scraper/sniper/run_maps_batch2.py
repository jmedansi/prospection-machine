"""Batch 2 — sectors still missing leads"""
import asyncio, sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scraper.main import main_async

CAMPAIGNS = [
    ("concessionnaire automobile", "Paris", 15, "concessionnaires_auto"),
    ("garage automobile", "Lyon", 15, "concessionnaires_auto"),
    ("plombier", "Paris", 15, "plomberie_chauffage"),
    ("chauffagiste", "Lyon", 10, "plomberie_chauffage"),
    ("dentiste", "Paris", 15, "sante"),
    ("osteopathe", "Lyon", 10, "sante"),
    ("peintre en batiment", "Paris", 10, "batiment"),
    ("electricien", "Lyon", 10, "batiment"),
    ("agence web", "Paris", 10, "informatique_web"),
    ("expert comptable", "Paris", 10, "expertise_comptable"),
    ("avocat", "Paris", 10, "avocat"),
]

async def run_all():
    total_leads = 0
    total_time = 0
    for i, (kw, city, limit, secteur) in enumerate(CAMPAIGNS, 1):
        print(f"\n{'='*60}")
        print(f"[{i}/{len(CAMPAIGNS)}] {kw} @ {city} (secteur={secteur}, limit={limit})")
        print(f"{'='*60}")
        start = time.time()
        try:
            await main_async(['--keyword', kw, '--city', city, '--limit', str(limit), '--secteur', secteur])
            elapsed = time.time() - start
            total_time += elapsed
            print(f"  -> {elapsed:.0f}s")
        except Exception as e:
            elapsed = time.time() - start
            print(f"  -> ERROR: {e} ({elapsed:.0f}s)")
        await asyncio.sleep(3)

    print(f"\n{'='*60}")
    print(f"Termine: {len(CAMPAIGNS)} campagnes en {total_time:.0f}s")

if __name__ == "__main__":
    asyncio.run(run_all())
