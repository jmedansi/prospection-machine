"""Batch 3 — 5 secteurs prioritaires, min-reviews 50, 20 leads/campagne"""
import asyncio, sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scraper.main import main_async

CAMPAIGNS = [
    # immobilier
    ("agence immobilière", "Paris", 20, "immobilier"),
    ("agent immobilier", "Paris", 20, "immobilier"),
    ("agence immobilière", "Lyon", 20, "immobilier"),
    ("agent immobilier", "Lyon", 20, "immobilier"),

    # courtage
    ("courtier immobilier", "Paris", 20, "courtage"),
    ("crédit immobilier", "Paris", 20, "courtage"),
    ("courtier immobilier", "Lyon", 20, "courtage"),
    ("crédit immobilier", "Lyon", 20, "courtage"),

    # garages (ex-concessionnaires_auto)
    ("garage", "Paris", 20, "garages"),
    ("garage", "Lyon", 20, "garages"),
    ("garage", "Marseille", 20, "garages"),
    ("garage", "Bordeaux", 20, "garages"),

    # cliniques_esthetiques
    ("clinique esthétique", "Paris", 20, "cliniques_esthetiques"),
    ("médecin esthétique", "Paris", 20, "cliniques_esthetiques"),
    ("clinique esthétique", "Lyon", 20, "cliniques_esthetiques"),
    ("médecin esthétique", "Lyon", 20, "cliniques_esthetiques"),

    # ecoles_formation
    ("centre de formation", "Paris", 20, "ecoles_formation"),
    ("formation professionnelle", "Paris", 20, "ecoles_formation"),
    ("centre de formation", "Lyon", 20, "ecoles_formation"),
    ("formation professionnelle", "Lyon", 20, "ecoles_formation"),
]

async def run_all():
    total_time = 0
    for i, (kw, city, limit, secteur) in enumerate(CAMPAIGNS, 1):
        print(f"\n{'='*60}")
        print(f"[{i}/{len(CAMPAIGNS)}] {kw} @ {city} (secteur={secteur}, limit={limit}, min-reviews=50)")
        print(f"{'='*60}")
        start = time.time()
        try:
            await main_async(['--keyword', kw, '--city', city, '--limit', str(limit), '--secteur', secteur, '--min-reviews', '50'])
            elapsed = time.time() - start
            total_time += elapsed
            print(f"  -> {elapsed:.0f}s")
        except Exception as e:
            elapsed = time.time() - start
            print(f"  -> ERROR: {e} ({elapsed:.0f}s)")
        await asyncio.sleep(5)

    print(f"\n{'='*60}")
    print(f"Terminé: {len(CAMPAIGNS)} campagnes en {total_time:.0f}s")

if __name__ == "__main__":
    asyncio.run(run_all())
