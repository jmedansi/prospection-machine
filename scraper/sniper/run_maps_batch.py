"""Run multiple maps scraping campaigns to rebuild sector leads"""
import asyncio, sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scraper.main import main_async

CAMPAIGNS = [
    # immobilier
    ("agent immobilier", "Paris", 15, "immobilier"),
    ("agence immobiliere", "Lyon", 15, "immobilier"),
    ("estimation immobiliere", "Marseille", 15, "immobilier"),

    # courtage
    ("courtier immobilier", "Paris", 10, "courtage"),
    ("credit immobilier", "Lyon", 10, "courtage"),

    # cliniques_esthetiques
    ("clinique esthetique", "Paris", 10, "cliniques_esthetiques"),
    ("medecin esthetique", "Lyon", 10, "cliniques_esthetiques"),

    # ecoles_formation
    ("formation professionnelle", "Paris", 10, "ecoles_formation"),
    ("centre de formation", "Lyon", 10, "ecoles_formation"),

    # concessionnaires_auto
    ("concessionnaire automobile", "Paris", 10, "concessionnaires_auto"),
    ("garage automobile", "Lyon", 10, "concessionnaires_auto"),

    # plomberie_chauffage
    ("plombier", "Paris", 10, "plomberie_chauffage"),
    ("chauffagiste", "Lyon", 10, "plomberie_chauffage"),

    # sante
    ("dentiste", "Paris", 10, "sante"),
    ("osteopathe", "Lyon", 10, "sante"),

    # batiment
    ("peintre en batiment", "Paris", 10, "batiment"),
    ("electricien", "Lyon", 10, "batiment"),

    # informatique_web
    ("agence web", "Paris", 10, "informatique_web"),
    ("developpeur web", "Lyon", 10, "informatique_web"),
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
        # Pause between runs
        await asyncio.sleep(5)

    print(f"\n{'='*60}")
    print(f"Termine: {len(CAMPAIGNS)} campagnes en {total_time:.0f}s")

if __name__ == "__main__":
    asyncio.run(run_all())
