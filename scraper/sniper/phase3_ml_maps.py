"""
Phase 3: Extraction ML sur leads Maps avec >50 avis.
Reutilise la logique de phase3_ml_maps() du pipeline.
"""
import sys, os, logging, concurrent.futures, time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.chdir(ROOT)

from database.connection import get_conn
from database.repos.leads_repo import LeadsRepo
from enrichisseur.extract_responsables_ml import extraire_responsables_ml

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("phase3")
fh = logging.FileHandler(os.path.join(ROOT, "logs", f"phase3_ml_{datetime.now().strftime('%Y-%m-%d')}.log"), encoding="utf-8")
fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(fh)

SECTEURS_MAPS = [
    "cliniques_esthetiques", "ecoles_formation", "courtage",
    "concessionnaires_auto", "plomberie_chauffage", "sante",
    "batiment", "avocat", "expertise_comptable"
]

def run():
    repo = LeadsRepo()
    logger.info(f"Phase 3 ML Maps — {len(SECTEURS_MAPS)} secteurs restants")
    
    for secteur in SECTEURS_MAPS:
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT id, nom, site_web FROM leads_bruts
                WHERE source IN ('maps', 'maps,ads') AND secteur=?
                  AND nb_avis > 50
                  AND site_web IS NOT NULL AND site_web != ''
                  AND (notes IS NULL OR notes = '')
                ORDER BY id
            """, (secteur,)).fetchall()
        
        if not rows:
            logger.info(f"  [{secteur}] aucun lead en attente")
            continue
        
        logger.info(f"  [{secteur}] {len(rows)} leads")
        ok = 0
        
        def _ml(r):
            return r['id'], extraire_responsables_ml(r['site_web'])
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            futures = {pool.submit(_ml, r): r for r in rows}
            for f in concurrent.futures.as_completed(futures, timeout=7200):
                r = futures[f]
                try:
                    lid, result = f.result(timeout=90)
                except concurrent.futures.TimeoutError:
                    logger.error(f"    #{r['id']} TIMEOUT ML")
                    repo.update_fields(r['id'], {"notes": "(timeout mentions legales)"})
                    continue
                except Exception as e:
                    logger.error(f"    #{r['id']} ERREUR: {e}")
                    repo.update_fields(r['id'], {"notes": f"(erreur: {str(e)[:100]})"})
                    continue
                
                if result:
                    repo.update_fields(r['id'], {"notes": result})
                    first = result.split("\n")[0].strip()[:60]
                    logger.info(f"    #{lid} -> {first}")
                    ok += 1
                else:
                    repo.update_fields(r['id'], {"notes": "(mentions legales introuvables)"})
                    logger.info(f"    #{lid} -> RIEN")
        
        logger.info(f"  [{secteur}] ML: {ok}/{len(rows)} OK")
    
    logger.info("Phase 3 TERMINEE")

if __name__ == "__main__":
    run()
