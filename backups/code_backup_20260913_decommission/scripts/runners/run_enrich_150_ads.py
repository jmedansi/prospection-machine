#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_enrich_150_ads.py

Enrichissement parallele de 150 leads Google Ads :
  1. Phase 1: CEO enrichment (3 workers) — API Gouv + Groq
  2. Phase 2: ML extraction (1 worker) — 500 mots mentions legales

Les deux phases tournent simultanement.
Monitoring en temps reel avec progress bar + logs detailles.

Usage:
  python run_enrich_150_ads.py
"""

import sys
import os
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional

# Setup path
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ══════════════════════════════════════════════════════════════════════════════
# LOGGING SETUP
# ══════════════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler(f"enrich_150_ads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# IMPORTS (après logging setup)
# ══════════════════════════════════════════════════════════════════════════════

from core.config import ensure_env
from database.repos.leads_repo import LeadsRepo
from sniper.enrichment.ceo_finder import find_ceo
from enrichisseur.extract_responsables_ml import extraire_responsables_ml

ensure_env()

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 1: CEO ENRICHMENT (3 workers)
# ══════════════════════════════════════════════════════════════════════════════

class CeoEnricher:
    def __init__(self, repo: LeadsRepo, leads: list, max_workers: int = 3):
        self.repo = repo
        self.leads = leads
        self.max_workers = max_workers
        self.success = 0
        self.failed = 0
        self.skipped = 0
        self.start_time = None
        self.end_time = None
        self.lock = threading.Lock()
        
    def enrich_one(self, lead: dict) -> tuple[int, dict | None]:
        """Enrichit un lead avec CEO. Retourne (lead_id, result_dict) ou (lead_id, None)."""
        lid = lead["id"]
        try:
            nom = lead.get("nom") or "Unknown"
            site_web = lead.get("site_web") or ""
            
            # Extraire le domaine
            domain = site_web.split("//")[-1].split("/")[0].lstrip("www.")
            if not domain:
                with self.lock:
                    self.skipped += 1
                logger.warning(f"  [SKIP] CEO #{lid}: domain vide")
                return lid, None
            
            # Appel find_ceo
            result = find_ceo(
                company_name=nom,
                domain=domain,
                url=site_web,
                pays=lead.get("pays", "fr"),
            )
            
            if not result.get("ceo_prenom") or not result.get("ceo_nom"):
                with self.lock:
                    self.failed += 1
                logger.debug(f"  CEO #{lid}: pas trouvé ({result['ceo_source']})")
                return lid, None
            
            # Mise à jour DB
            self.repo.update_fields(
                lid,
                {
                    "ceo_prenom": result["ceo_prenom"],
                    "ceo_nom": result["ceo_nom"],
                    "ceo_source": result["ceo_source"],
                }
            )
            with self.lock:
                self.success += 1
            logger.info(f"[OK] CEO #{lid}: {result['ceo_prenom']} {result['ceo_nom']} ({result['ceo_source']})")
            return lid, result
            
        except Exception as e:
            with self.lock:
                self.failed += 1
            logger.error(f"[ERR] CEO #{lid}: {type(e).__name__}: {e}")
            return lid, None
    
    def run(self) -> dict:
        """Lance l'enrichissement CEO en parallèle. Retourne stats."""
        logger.info(f"\n{'='*80}")
        logger.info(f"PHASE 1: CEO ENRICHMENT ({len(self.leads)} leads, {self.max_workers} workers)")
        logger.info(f"{'='*80}")
        
        self.start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {
                pool.submit(self.enrich_one, lead): lead["id"]
                for lead in self.leads
            }
            
            completed = 0
            for future in as_completed(futures, timeout=3600):  # 1h timeout
                completed += 1
                try:
                    lid, result = future.result(timeout=90)
                    if completed % 10 == 0:
                        elapsed = time.time() - self.start_time
                        rate = completed / elapsed if elapsed > 0 else 0
                        logger.info(f"  [{completed}/{len(self.leads)}] {rate:.1f}/sec | OK:{self.success} ERR:{self.failed} SKIP:{self.skipped}")
                except Exception as e:
                    lid = futures[future]
                    with self.lock:
                        self.failed += 1
                    logger.error(f"[ERR] CEO #{lid}: timeout ou erreur fatale — {e}")
        
        self.end_time = time.time()
        duration = self.end_time - self.start_time
        
        stats = {
            "phase": "CEO Enrichment",
            "total": len(self.leads),
            "success": self.success,
            "failed": self.failed,
            "skipped": self.skipped,
            "duration_sec": duration,
            "rate_per_sec": len(self.leads) / duration if duration > 0 else 0,
        }
        
        logger.info(f"\nRésumé CEO:")
        logger.info(f"  [OK] Succes: {self.success}/{len(self.leads)}")
        logger.info(f"  [ERR] Erreurs: {self.failed}")
        logger.info(f"  [SKIP] Skipped: {self.skipped}")
        logger.info(f"  [TIME] Duree: {duration:.1f}s ({stats['rate_per_sec']:.1f}/sec)")
        
        return stats


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 2: ML EXTRACTION (1 worker)
# ══════════════════════════════════════════════════════════════════════════════

class MlExtractor:
    def __init__(self, repo: LeadsRepo, leads: list, max_workers: int = 1):
        self.repo = repo
        self.leads = leads
        self.max_workers = max_workers
        self.success = 0
        self.failed = 0
        self.skipped = 0
        self.start_time = None
        self.end_time = None
        self.lock = threading.Lock()
        
    def extract_one(self, lead: dict) -> tuple[int, str | None]:
        """Extrait 500 mots ML d'un lead. Retourne (lead_id, text) ou (lead_id, None)."""
        lid = lead["id"]
        try:
            site_web = lead.get("site_web") or ""
            if not site_web:
                with self.lock:
                    self.skipped += 1
                logger.debug(f"  [SKIP] ML #{lid}: site_web vide")
                return lid, None
            
            # Appel extraction
            text = extraire_responsables_ml(site_web)
            
            if not text:
                with self.lock:
                    self.failed += 1
                logger.debug(f"  ML #{lid}: texte vide ou inaccessible")
                return lid, None
            
            # Mise à jour DB
            ml_json = json.dumps(
                {"raw_text": text, "extracted_at": datetime.now().isoformat()},
                ensure_ascii=False
            )
            self.repo.update_fields(lid, {"ml_extracted": ml_json})
            
            with self.lock:
                self.success += 1
            word_count = len(text.split())
            logger.info(f"[OK] ML #{lid}: {word_count} words extracted")
            return lid, text
            
        except Exception as e:
            with self.lock:
                self.failed += 1
            logger.error(f"[ERR] ML #{lid}: {type(e).__name__}: {e}")
            return lid, None
    
    def run(self) -> dict:
        """Lance l'extraction ML en parallèle. Retourne stats."""
        logger.info(f"\n{'='*80}")
        logger.info(f"PHASE 2: ML EXTRACTION ({len(self.leads)} leads, {self.max_workers} worker)")
        logger.info(f"{'='*80}")
        
        self.start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {
                pool.submit(self.extract_one, lead): lead["id"]
                for lead in self.leads
            }
            
            completed = 0
            for future in as_completed(futures, timeout=7200):  # 2h timeout
                completed += 1
                try:
                    lid, text = future.result(timeout=120)
                    if completed % 10 == 0:
                        elapsed = time.time() - self.start_time
                        rate = completed / elapsed if elapsed > 0 else 0
                        logger.info(f"  [{completed}/{len(self.leads)}] {rate:.1f}/sec | OK:{self.success} ERR:{self.failed} SKIP:{self.skipped}")
                except Exception as e:
                    lid = futures[future]
                    with self.lock:
                        self.failed += 1
                    logger.error(f"✗ ML #{lid}: timeout ou erreur fatale — {e}")
        
        self.end_time = time.time()
        duration = self.end_time - self.start_time
        
        stats = {
            "phase": "ML Extraction",
            "total": len(self.leads),
            "success": self.success,
            "failed": self.failed,
            "skipped": self.skipped,
            "duration_sec": duration,
            "rate_per_sec": len(self.leads) / duration if duration > 0 else 0,
        }
        
        logger.info(f"\nRésumé ML:")
        logger.info(f"  [OK] Succes: {self.success}/{len(self.leads)}")
        logger.info(f"  [ERR] Erreurs: {self.failed}")
        logger.info(f"  [SKIP] Skipped: {self.skipped}")
        logger.info(f"  [TIME] Duree: {duration:.1f}s ({stats['rate_per_sec']:.1f}/sec)")
        
        return stats


# ══════════════════════════════════════════════════════════════════════════════
# MAIN: Parallel orchestration
# ══════════════════════════════════════════════════════════════════════════════

def main():
    """Récupère 150 leads Google Ads + lance Phases 1 & 2 en parallèle."""
    
    logger.info(f"\n{'#'*80}")
    logger.info(f"DÉMARRAGE: Enrichissement 150 Google Ads Leads")
    logger.info(f"{'#'*80}")
    
    repo = LeadsRepo()
    
    # ──────────────────────────────────────────────────────────────────────────
    # Phase 0: Récupération des 150 leads
    # ──────────────────────────────────────────────────────────────────────────
    logger.info("\n[Phase 0] Recuperation des 150 derniers leads Google Ads...")
    try:
        result = repo.get_all(
            source="ads",  # Google Ads source
            statut="tous",
            limit=150,
            page=1,
        )
        leads = result.get("leads", [])
        logger.info(f"[OK] {len(leads)} leads recuperes")
        
        if not leads:
            logger.error("[ERREUR] Aucun lead Google Ads trouve!")
            return
        
    except Exception as e:
        logger.error(f"✗ Erreur récupération leads: {e}")
        return
    
    # ──────────────────────────────────────────────────────────────────────────
    # Phase 1 & 2: Lancer en parallèle via threads
    # ──────────────────────────────────────────────────────────────────────────
    logger.info(f"\n[Setup] Lancement des deux phases en parallèle...")
    
    ceo_enricher = CeoEnricher(repo, leads, max_workers=3)
    ml_extractor = MlExtractor(repo, leads, max_workers=1)
    
    # Lancer dans deux threads séparés
    thread_ceo = threading.Thread(target=lambda: ceo_enricher.run(), daemon=False)
    thread_ml = threading.Thread(target=lambda: ml_extractor.run(), daemon=False)
    
    thread_ceo.start()
    thread_ml.start()
    
    # Attendre que les deux terminent
    thread_ceo.join()
    thread_ml.join()
    
    # ──────────────────────────────────────────────────────────────────────────
    # Résumé final
    # ──────────────────────────────────────────────────────────────────────────
    logger.info(f"\n{'='*80}")
    logger.info(f"RÉSUMÉ FINAL")
    logger.info(f"{'='*80}")
    logger.info(f"\n[OK] CEO Enrichment: {ceo_enricher.success}/{len(leads)} ({100*ceo_enricher.success/len(leads):.1f}%)")
    logger.info(f"[OK] ML Extraction:  {ml_extractor.success}/{len(leads)} ({100*ml_extractor.success/len(leads):.1f}%)")
    
    total_time = max(ceo_enricher.end_time or 0, ml_extractor.end_time or 0) - min(ceo_enricher.start_time or time.time(), ml_extractor.start_time or time.time())
    logger.info(f"\n[TIME] Duree totale: {total_time:.1f}s")
    logger.info(f"\n[DONE] Enrichissement termine! Verifier les logs pour les details.")


if __name__ == "__main__":
    main()
