# -*- coding: utf-8 -*-
"""
Pipeline nocturne : 3 phases indépendantes
Phase 1: Scraping Ads uniquement (search_one -> insert_lead)
Phase 2: Enrichissement email + CEO sur tous les leads Ads
Phase 3: Extraction responsables ML sur leads Maps (+50 avis)
"""

import asyncio
import logging
import subprocess
import sys
import os
import random
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scraper.sniper.headless_extract import search_one
from database.leads import insert_lead
from database.connection import get_conn

SEARCH_TIMEOUT = 60

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("overnight")

LOG_DIR = os.path.join(ROOT, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
log_file = os.path.join(LOG_DIR, f"overnight_ads_{datetime.now().strftime('%Y-%m-%d')}.log")
fh = logging.FileHandler(log_file, encoding="utf-8")
fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(fh)

SECTEURS = {
    "immobilier": {
        "keywords": [
            "agence immobiliere", "agent immobilier", "estimation immobiliere",
            "achat appartement", "vente maison", "promoteur immobilier",
            "notaire", "syndic de copropriete", "gestion locative",
            "diagnostiqueur immobilier", "investissement locatif", "viager",
        ],
    },
    "courtage": {
        "keywords": [
            "courtier immobilier", "courtier pret immobilier",
            "simulation credit immobilier", "rachat de credit",
            "pret immobilier", "assurance pret", "meilleur taux immobilier",
            "banque privee", "conseiller financier", "gestion de patrimoine",
            "credit consommation", "courtier en financement",
        ],
    },
    "cliniques_esthetiques": {
        "keywords": [
            "medecine esthetique", "chirurgie esthetique", "clinique esthetique",
            "dermatologue esthetique", "injection acide hyaluronique",
            "medecine anti-age", "laser esthetique", "epilation laser",
            "centre esthetique", "chirurgie plastique", "rhinoplastie",
            "liposuccion",
        ],
    },
    "ecoles_formation": {
        "keywords": [
            "centre de formation", "formation professionnelle",
            "formation comptabilite", "reconversion professionnelle",
            "formation management", "formation informatique", "formation RH",
            "CFA alternance", "ecole de commerce", "formation marketing",
            "formation langues", "formation BTS",
        ],
    },
}

VILLES = ["Paris", "Lyon", "Marseille", "Bordeaux", "Lille"]
PORT_BASE = 9600


def _kill_chrome(on_port: int = None):
    try:
        if on_port:
            r = subprocess.run(['netstat', '-ano'], capture_output=True, text=True, timeout=5)
            for l in r.stdout.split('\n'):
                if f':{on_port}' in l and 'LISTENING' in l:
                    parts = l.strip().split()
                    if parts:
                        subprocess.run(['taskkill', '/PID', parts[-1], '/F'], capture_output=True, timeout=3)
        else:
            r = subprocess.run(['tasklist', '/NH', '/FI', 'IMAGENAME eq chrome.exe'], capture_output=True, text=True, timeout=5)
            for l in r.stdout.split('\n'):
                if 'chrome.exe' in l:
                    parts = l.strip().split()
                    if parts:
                        subprocess.run(['taskkill', '/PID', parts[1], '/F'], capture_output=True, timeout=3)
    except:
        pass


def clean_url(url: str) -> str | None:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    url = url.replace("http://", "https://")
    return url.rstrip("/")


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 1: SCRAPING ADS UNIQUEMENT
# ═══════════════════════════════════════════════════════════════════════════════

async def phase1_scrape() -> dict:
    """Scrape les annonces Ads pour tous les secteurs. Retourne {secteur: [lead_ids]}."""
    all_leads = {}

    for secteur, cfg in SECTEURS.items():
        keywords = cfg["keywords"]
        total = len(keywords) * len(VILLES)
        seen = set()
        frais = 0
        tries = 0
        secteur_ids = []

        logger.info(f"\n{'='*50}")
        logger.info(f"PHASE 1 - SECTEUR: {secteur} ({total} keywords)")
        logger.info(f"{'='*50}")

        for kw in keywords:
            for ville in VILLES:
                if tries >= total:
                    break
                tries += 1
                query = f"{kw} {ville}"
                port = PORT_BASE + (tries % 50)

                logger.info(f"  [{tries}/{total}] {query}")
                try:
                    domains = await asyncio.wait_for(search_one(query, port), timeout=SEARCH_TIMEOUT)
                except asyncio.TimeoutError:
                    logger.error(f"    TIMEOUT > {SEARCH_TIMEOUT}s")
                    _kill_chrome()
                    continue
                except Exception as e:
                    logger.error(f"    ERREUR: {e}")
                    continue
                finally:
                    _kill_chrome(on_port=port)

                if not domains:
                    continue

                for raw_url in domains:
                    url = clean_url(raw_url)
                    if not url or url in seen:
                        continue
                    seen.add(url)

                    lid = insert_lead({
                        "nom": url.replace("https://", "").replace("http://", "").rstrip("/"),
                        "site_web": url,
                        "telephone": "",
                        "ville": ville,
                        "mot_cle": query,
                        "source": "ads",
                        "secteur": secteur,
                        "rating": 0,
                    })
                    if not lid:
                        continue

                    frais += 1
                    secteur_ids.append(lid)
                    logger.info(f"    [OK] #{lid} {url}")

                await asyncio.sleep(random.randint(8, 15))

        all_leads[secteur] = secteur_ids
        logger.info(f"  => {secteur}: {frais} nouveaux leads")

    return all_leads


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 2: ENRICHISSEMENT EMAIL + CEO
# ═══════════════════════════════════════════════════════════════════════════════

def _enrichir_un_lead(lid: int, url: str, nom: str):
    """Email + CEO pour un lead (synchrone, avec timeout global)."""
    from scraper.email_finder import find_email_all_methods
    from urllib.parse import urlparse
    from sniper.enrichment.ceo_finder import find_ceo

    domain = urlparse(url).netloc.lstrip("www.") or url
    updates = {}

    try:
        ef = find_email_all_methods(url, fast_mode=True)
        if ef.get("email"):
            updates["email"] = ef["email"]
            updates["email_valide"] = ef.get("source", "")
    except Exception as e:
        logger.error(f"    email #{lid} ({url}): {e}")

    try:
        ceo = find_ceo(nom or domain, domain, url)
        if ceo.get("ceo_prenom_norm"):
            updates["prenom_gerant"] = ceo["ceo_prenom_norm"]
        if ceo.get("ceo_nom_norm"):
            updates["nom_gerant"] = ceo["ceo_nom_norm"]
    except Exception as e:
        logger.error(f"    ceo #{lid} ({url}): {e}")

    return lid, updates


def phase2_enrichir(secteur: str, lead_ids: list[int]):
    """Enrichit les leads d'un secteur avec email + CEO. Timeout 30s par lead."""
    import concurrent.futures
    from database.connection import get_conn

    logger.info(f"\n  Enrichissement {secteur}: {len(lead_ids)} leads")

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = []
        for lid in lead_ids:
            with get_conn() as conn:
                row = conn.execute("SELECT id, nom, site_web FROM leads_bruts WHERE id=?", (lid,)).fetchone()
            if not row:
                continue
            f = pool.submit(_enrichir_un_lead, lid, row["site_web"], row["nom"])
            futures.append(f)

        ok = 0
        for f in concurrent.futures.as_completed(futures, timeout=600):
            try:
                lid, updates = f.result(timeout=30)
            except concurrent.futures.TimeoutError:
                logger.error(f"    TIMEOUT enrich #{lid}")
                continue
            except Exception as e:
                logger.error(f"    ERREUR enrich: {e}")
                continue

            if updates:
                with get_conn() as conn:
                    set_clause = ", ".join(f"{k}=?" for k in updates)
                    conn.execute(f"UPDATE leads_bruts SET {set_clause} WHERE id=?", list(updates.values()) + [lid])
                    conn.commit()

            email = updates.get("email", "-")
            ceo_str = f"{updates.get('prenom_gerant', '') or ''} {updates.get('nom_gerant', '') or ''}".strip() or "-"
            logger.info(f"    #{lid} email={email} ceo={ceo_str}")
            ok += 1

    return ok


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 3: ML NOTES SUR MAPS
# ═══════════════════════════════════════════════════════════════════════════════

def phase3_ml_maps(secteurs: list[str]):
    """Extrait les responsables ML sur leads Maps (>50 avis). Timeout 90s par lead."""
    import concurrent.futures
    from enrichisseur.mentions_legales_enricher import enrichir_lead, _format_notes, update_db
    from database.repos.leads_repo import LeadsRepo

    repo = LeadsRepo()
    logger.info(f"\n{'='*50}")
    logger.info("PHASE 3: ML sur leads Maps (+50 avis)")
    logger.info(f"{'='*50}")

    for secteur in secteurs:
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT id, nom, site_web FROM leads_bruts
                WHERE source='maps' AND secteur=?
                  AND nb_avis > 50
                  AND site_web IS NOT NULL AND site_web != ''
                  AND (notes IS NULL OR notes = '')
                ORDER BY id
            """, (secteur,)).fetchall()

        if not rows:
            logger.info(f"  [{secteur}] aucun lead Maps en attente")
            continue

        logger.info(f"  [{secteur}] {len(rows)} leads")
        ok = 0

        def _ml_un_lead(r):
            return r['id'], enrichir_lead(r['id'], r['site_web'], r['nom'])

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            futures = {pool.submit(_ml_un_lead, r): r for r in rows}
            for f in concurrent.futures.as_completed(futures, timeout=600):
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

                notes = _format_notes(result) if result else ""
                if notes:
                    update_db(lid, notes, result)
                    logger.info(f"    #{lid} -> {notes[:60]}")
                    ok += 1
                else:
                    update_db(lid, "(mentions legales introuvables)", result or {
                        "dirigeant_prenom": None,
                        "dirigeant_nom": None,
                        "emails": [],
                        "telephones": [],
                        "url_trouvee": None
                    })
                    logger.info(f"    #{lid} -> RIEN")

        logger.info(f"  [{secteur}] ML: {ok}/{len(rows)} OK")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

async def main():
    logger.info("="*60)
    logger.info("OVERNIGHT ADS PIPELINE")
    logger.info(f"Date: {datetime.now().isoformat()}")
    logger.info(f"Secteurs: {', '.join(SECTEURS.keys())}")
    logger.info(f"Log: {log_file}")
    logger.info("="*60)

    # PHASE 1 - Scraping (rapide)
    logger.info(f"\n{'='*60}")
    logger.info("PHASE 1: SCRAPING ADS")
    logger.info(f"{'='*60}")
    all_leads = await phase1_scrape()

    total = sum(len(v) for v in all_leads.values())
    logger.info(f"\n{'='*60}")
    logger.info(f"PHASE 1 TERMINEE: {total} nouveaux leads au total")
    for s, ids in all_leads.items():
        logger.info(f"  {s}: {len(ids)} leads")
    logger.info(f"{'='*60}")

    if total == 0:
        logger.info("Aucun lead trouve, saute phases 2 et 3")
        logger.info(f"\nFIN: {datetime.now().isoformat()}")
        return

    # PHASE 2 - Enrichissement (email + CEO)
    logger.info(f"\n{'='*60}")
    logger.info("PHASE 2: ENRICHISSEMENT EMAIL + CEO")
    logger.info(f"{'='*60}")
    for secteur, ids in all_leads.items():
        if ids:
            n = phase2_enrichir(secteur, ids)
            logger.info(f"  [{secteur}] {n}/{len(ids)} enrichis")

    # PHASE 3 - ML Maps
    phase3_ml_maps(list(SECTEURS.keys()))

    logger.info(f"\n{'='*60}")
    logger.info(f"FIN: {datetime.now().isoformat()}")
    logger.info(f"Log: {log_file}")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
