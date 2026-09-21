"""
ML extraction pour tous les leads avec site web + notes vides (tous secteurs, toutes sources).
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S", stream=sys.stdout, force=True)
logger = logging.getLogger("ml_all")
fh = logging.FileHandler(os.path.join(ROOT, "logs", f"ml_all_{datetime.now().strftime('%Y-%m-%d')}.log"), encoding="utf-8")
fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(fh)

# Domaines de plateformes tierces où la page ML ne contiendra PAS les infos du lead
_TIER_PLATFORMS = [
    "doctolib.fr", "meilleurtaux", "bymycar.fr",
    "bouygues-immobilier.com", "leboncoin.fr",
    "privateaser.com", "calendly.com",
    "trouvermonartisan", "stootie",
]

def _est_plateforme_tierce(site_web: str) -> bool:
    if not site_web:
        return False
    site = site_web.lower()
    return any(p in site for p in _TIER_PLATFORMS)

def get_secteurs():
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT DISTINCT secteur FROM leads_bruts
            WHERE site_web IS NOT NULL AND site_web != ''
              AND (notes IS NULL OR notes = '')
            ORDER BY secteur
        """).fetchall()
    return [r[0] for r in rows]

def get_leads(secteur):
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT id, nom, site_web FROM leads_bruts
            WHERE secteur=?
              AND site_web IS NOT NULL AND site_web != ''
              AND (notes IS NULL OR notes = '')
            ORDER BY id
        """, (secteur,)).fetchall()
    # Filtrer les plateformes tierces
    return [dict(r) for r in rows if not _est_plateforme_tierce(r["site_web"])]

def run():
    repo = LeadsRepo()
    secteurs = get_secteurs()
    logger.info(f"Secteurs a traiter: {secteurs}")
    total_global = 0
    for handler in logger.handlers:
        handler.flush()

    for secteur in secteurs:
        leads = get_leads(secteur)
        if not leads:
            continue
        total_global += len(leads)
        logger.info(f"\n  [{secteur}] {len(leads)} leads")
        ok = 0

        def _ml(r):
            return r['id'], extraire_responsables_ml(r['site_web'])

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            futures = {pool.submit(_ml, r): r for r in leads}
            for f in concurrent.futures.as_completed(futures, timeout=7200):
                r = futures[f]
                try:
                    lid, result = f.result(timeout=90)
                except concurrent.futures.TimeoutError:
                    logger.error(f"    #{r['id']} TIMEOUT (notes laissee vide)")
                    continue
                except Exception as e:
                    logger.error(f"    #{r['id']} ERREUR: {e} (notes laissee vide)")
                    continue

                if result:
                    repo.update_fields(r['id'], {"notes": result})
                    first = result.split("\n")[0].strip()[:60]
                    logger.info(f"    #{lid} -> {first}")
                    ok += 1
                else:
                    # Ne PAS écrire de placeholder — laisser notes vide
                    logger.info(f"    #{lid} -> RIEN (notes laissée vide)")

                # Forcer l'écriture des logs sur le disque
                for h in logger.handlers:
                    h.flush()

                # Throttle : 1.5s entre chaque lead
                time.sleep(1.5)

        logger.info(f"  [{secteur}] OK: {ok}/{len(leads)}")

    logger.info(f"\n=== TERMINE: {total_global} leads traites ===")

if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        import traceback
        logger.error(f"FATAL: {e}")
        with open(os.path.join(ROOT, "logs", "ml_all_crash.log"), "w") as f:
            traceback.print_exc(file=f)
        raise
