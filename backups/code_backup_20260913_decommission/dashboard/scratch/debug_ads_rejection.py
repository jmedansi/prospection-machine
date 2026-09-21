
import sys
import os
import logging
import asyncio

# Ajout du répertoire racine au path
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Configuration du logging pour voir les REJET dans la console
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

from scraper.sniper.pipeline import SniperPipeline

def debug_ads():
    print("\n" + "="*60)
    print("DEBUG SNIPER ADS: avocat france")
    print("="*60)
    
    pipeline = SniperPipeline()
    # On limite à 3 pour aller vite et voir les rejets
    results = pipeline.run(
        keywords=["avocat france"],
        country="fr",
        max_per_kw=5,
        pages_per_kw=1,
        parallel_enrich=1 # Un par un pour bien lire les logs
    )
    
    print("\n" + "="*60)
    print("RÉSULTATS DU DEBUG")
    print(f"Acceptés : {results.get('accepted')}")
    print(f"Rejetés  : {results.get('rejected')}")
    print(f"Erreurs  : {results.get('errors')}")
    print("="*60)

if __name__ == "__main__":
    debug_ads()
