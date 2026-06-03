# -*- coding: utf-8 -*-
"""
scraper/sniper/tech_scraper.py — Source 2 : Entreprises par tech stack

Lire scraper/sniper/TECH_SCRAPER_README.md avant toute modification.

Flux :
  Phase 1  → API recherche-entreprises.api.gouv.fr (par code NAF + effectif ≥ 10)
  Phase 2  → Wappalyzer  ← détecte le CMS / e-commerce / CDN
  Phase 3  → PageSpeed   ← seulement si CMS à budget signal (HIGH_VALUE_CMS)
  Phase 4  → scoring.py  ← tag_urgence + niveau_urgence
  Phase 5  → DB          ← INSERT leads_bruts source='tech'

Différence avec Source 1 (Ads) :
  - Pas de Google Ads scraping — les entreprises sont trouvées via leur NAF + taille
  - Signal de budget = CMS coûteux (WordPress+WooCommerce, PrestaShop, Magento, Shopify)
    au lieu d'un achat de pubs

Usage programmatique :
    from scraper.sniper.tech_scraper import TechScraper
    s = TechScraper()
    s.run(naf_codes=["6201Z", "7311Z"], max_companies=200, max_leads=30)
"""

import concurrent.futures
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ─── Constantes ──────────────────────────────────────────────────────────────

SIRENE_API    = "https://recherche-entreprises.api.gouv.fr/search"
_PAGE_SIZE    = 25          # Max autorisé par l'API
_REQUEST_TIMEOUT = 12
_INTER_REQUEST   = 0.25     # délai entre pages API (politesse)

# Codes NAF ciblés — B2B digital/tech (partagé avec bodacc_scanner)
DEFAULT_NAF = [
    "6201Z", "6202A", "6202B", "6203Z", "6209Z",   # Informatique
    "7311Z", "7312Z", "7320Z",                       # Pub / marketing
    "7022Z", "7021Z", "7490B",                       # Conseil / PR
    "6311Z", "6312Z",                                # Data / hébergement
    "5829A", "5829B", "5829C",                       # Édition logiciel
    "4651Z", "4652Z",                                # Commerce gros IT
]

# Tranches effectif salarié (INSEE) — on ne cible pas les micro-entreprises
_MIN_EFFECTIF_CODES = {
    "11",   # 10-19
    "12",   # 20-49
    "21",   # 50-99
    "22",   # 100-199
    "31",   # 200-249
    "32",   # 250-499
    "41",   # 500-999
    "42",   # 1000-1999
    "51",   # 2000-4999
    "52",   # 5000-9999
    "53",   # 10000+
}

# CMS auto-gérés = aucun prestataire web impliqué → pas de budget pour nous
# Tout ce qui N'est PAS dans cette liste est accepté : full-code, CMS premium,
# framework JS, headless, etc.
_AUTOGEREE_CMS = {
    "Wix", "Squarespace", "Weebly", "Jimdo", "Webflow",
    "Blogger", "Tumblr", "GoDaddy Website Builder",
    "Strikingly", "Carrd", "Notion", "Site123",
}


# ─── État partagé (pollable par le dashboard) ─────────────────────────────────

_state: Dict = {
    "running":       False,
    "phase":         None,
    "total_fetched": 0,
    "wap_done":      0,
    "accepted":      0,
    "rejected":      0,
    "errors":        0,
    "logs":          [],
    "started_at":    None,
    "ended_at":      None,
}


def get_state() -> Dict:
    return dict(_state)


def reset_state() -> None:
    _state["running"] = False
    _state["phase"]   = None


def _log(msg: str, level: str = "info"):
    getattr(logger, level)(msg)
    _state["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    if len(_state["logs"]) > 50:
        _state["logs"].pop(0)


# ─── Phase 1 : Fetch API Entreprises ─────────────────────────────────────────

def _fetch_companies_by_naf(
    naf_code: str,
    max_companies: int,
) -> list[dict]:
    """
    Récupère des entreprises avec site_internet pour un code NAF donné.
    Filtre client-side sur effectif >= 10 salariés.

    Returns:
        Liste de dicts {siren, nom, site_web, ville, naf}
    """
    results = []
    page    = 1

    while len(results) < max_companies:
        try:
            resp = requests.get(
                SIRENE_API,
                params={
                    "activite_principale": naf_code,
                    "per_page": _PAGE_SIZE,
                    "page": page,
                },
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"API Entreprises NAF {naf_code} page {page} : {e}")
            break

        batch = data.get("results") or []
        if not batch:
            break

        for c in batch:
            siege = c.get("siege") or {}

            # Filtre effectif
            effectif_code = (
                siege.get("tranche_effectif_salarie")
                or c.get("tranche_effectif_salarie")
                or "00"
            )
            if effectif_code not in _MIN_EFFECTIF_CODES:
                continue

            # Site web obligatoire
            site_web = (siege.get("site_internet") or "").strip().rstrip("/")
            if not site_web:
                continue
            if not site_web.startswith("http"):
                site_web = "https://" + site_web

            results.append({
                "siren":   c.get("siren") or c.get("siret", "")[:9],
                "nom":     c.get("nom_raison_sociale") or c.get("nom_complet") or "",
                "site_web": site_web,
                "ville":   siege.get("commune") or siege.get("libelle_commune") or "",
                "naf":     naf_code,
            })

        total = data.get("total_results", 0)
        if page * _PAGE_SIZE >= total or not batch:
            break
        page += 1
        time.sleep(_INTER_REQUEST)

    return results[:max_companies]


# ─── Phase 2 : Wappalyzer ─────────────────────────────────────────────────────

def _run_wappalyzer(site_web: str) -> dict:
    try:
        from scraper.sniper.wappalyzer_runner import analyze
        return analyze(site_web, timeout=30)
    except Exception as e:
        logger.debug(f"Wappalyzer {site_web} : {e}")
        return {"cms": None, "cdn": None, "ecommerce": None, "server": None,
                "technologies": [], "error": str(e)}


# ─── Phase 3 : PageSpeed (seulement si CMS à budget signal) ──────────────────

def _run_pagespeed(site_web: str) -> dict:
    try:
        from auditeur.agents.web_analyzer import run_pagespeed
        return run_pagespeed(site_web, "mobile") or {}
    except Exception as e:
        logger.debug(f"PageSpeed {site_web} : {e}")
        return {}


# ─── Phase 4 + 5 : Scoring → DB ──────────────────────────────────────────────

def _score_and_store(company: dict, wap: dict, pagespeed: dict) -> bool:
    """
    Applique le scoring et insère le lead qualifié en base.
    Retourne True si accepté, False si rejeté.
    """
    from scraper.sniper.scoring import score_lead, build_donnees_audit
    from database import insert_lead, get_conn

    result = score_lead(pagespeed, wap, source="tech")
    if result is None:
        return False

    tag, niveau, reason = result

    # CEO data (non disponible à ce stade — sera enrichi à la demande)
    donnees = build_donnees_audit(pagespeed, wap, tag, niveau, reason)

    # Déduplication SIREN
    siren = company.get("siren")
    if siren:
        with get_conn() as conn:
            existing = conn.execute(
                "SELECT id FROM leads_bruts WHERE donnees_audit LIKE ? AND source='tech'",
                (f'%"siren":"{siren}"%',)
            ).fetchone()
            if existing:
                logger.debug(f"Tech — SIREN {siren} déjà présent, ignoré")
                return False

        # Injecter SIREN dans les données audit
        donnees_dict = json.loads(donnees)
        donnees_dict["siren"] = siren
        donnees = json.dumps(donnees_dict, ensure_ascii=False)

    lead_id = insert_lead({
        "nom":            company["nom"],
        "adresse":        "",
        "ville":          company.get("ville", ""),
        "site_web":       company["site_web"],
        "telephone":      "",
        "email":          "",
        "mot_cle":        company.get("naf", ""),
        "category":       f"Tech Stack — {company.get('naf', '')}",
        "source":         "tech",
        "tag_urgence":    tag,
        "niveau_urgence": niveau,
        "donnees_audit":  donnees,
        "statut":         "en_attente",
    })

    if lead_id:
        cms = wap.get("cms") or wap.get("ecommerce") or "?"
        _log(f"  ✓  {company['site_web']} — {tag} niv.{niveau} | {cms} | {reason[:60]}")
        return True

    return False


# ─── Orchestrateur ────────────────────────────────────────────────────────────

class TechScraper:
    """
    Scraper Source 2 — tech stack via API Entreprises + Wappalyzer + PageSpeed.

    Usage :
        s = TechScraper()
        s.run(naf_codes=["6201Z"], max_companies=200, max_leads=30)
    """

    def run(
        self,
        naf_codes:     Optional[List[str]] = None,
        max_companies: int = 300,    # entreprises examinées au total
        max_leads:     int = 50,     # leads insérés au maximum
        parallel:      int = 3,      # threads pour Wap + PageSpeed
        campaign_name: Optional[str] = None,
    ) -> Dict:
        """
        Exécute le pipeline tech complet.

        Args:
            naf_codes:     codes NAF à cibler (défaut : DEFAULT_NAF)
            max_companies: limite d'entreprises fetchées au total
            max_leads:     limite d'insertions en base
            parallel:      threads d'enrichissement
            campaign_name: nom de la campagne DB

        Returns:
            {"accepted": int, "rejected": int, "errors": int, "campaign_id": int}
        """
        if _state["running"]:
            return {"error": "TechScraper déjà en cours"}

        _state.update({
            "running": True, "phase": "fetch",
            "total_fetched": 0, "wap_done": 0,
            "accepted": 0, "rejected": 0, "errors": 0,
            "logs": [], "started_at": datetime.now().isoformat(), "ended_at": None,
        })

        if naf_codes is None:
            naf_codes = DEFAULT_NAF

        try:
            # ── Créer la campagne ─────────────────────────────────────────────
            from database import insert_campaign
            if not campaign_name:
                campaign_name = f"Sniper Tech — {datetime.now().strftime('%d/%m %H:%M')}"
            campaign_id = insert_campaign(campaign_name, "tech", "fr")
            _log(f"Campagne créée : #{campaign_id} — {campaign_name}")

            # ── Phase 1 : Fetch API Entreprises ──────────────────────────────
            _state["phase"] = "fetch"
            per_naf = max(1, max_companies // len(naf_codes))
            _log(f"Phase 1 — Fetch API Entreprises ({len(naf_codes)} codes NAF, max {per_naf}/code)")

            all_companies: list[dict] = []
            seen_sirens:   set        = set()

            for naf in naf_codes:
                batch = _fetch_companies_by_naf(naf, per_naf)
                # Déduplication inter-codes NAF
                for c in batch:
                    siren = c.get("siren")
                    if siren and siren in seen_sirens:
                        continue
                    if siren:
                        seen_sirens.add(siren)
                    all_companies.append(c)

            _state["total_fetched"] = len(all_companies)
            _log(f"  {len(all_companies)} entreprises avec site_internet récupérées")

            if not all_companies:
                _log("Aucune entreprise trouvée — vérifier les codes NAF ou la connexion")
                return {"accepted": 0, "rejected": 0, "errors": 0, "campaign_id": campaign_id}

            # ── Phase 2+3+4+5 : Wap → PageSpeed → Scoring → DB (parallèle) ──
            _state["phase"] = "enrichissement"
            _log(f"Phase 2 — Wappalyzer + scoring ({parallel} threads, max {max_leads} leads)")

            def _process(company: dict) -> bool:
                """Wap → PageSpeed conditionnel → score → store."""
                try:
                    wap = _run_wappalyzer(company["site_web"])
                    _state["wap_done"] += 1

                    # Filtre rapide : rejeter seulement les CMS auto-gérés (Wix, Squarespace…)
                    # Un site full-code (cms=None) ou tout autre CMS est accepté
                    cms = wap.get("cms") or wap.get("ecommerce")
                    if cms and cms in _AUTOGEREE_CMS:
                        return False

                    # PageSpeed pour tous les sites non-rejetés
                    pagespeed = _run_pagespeed(company["site_web"])

                    return _score_and_store(company, wap, pagespeed)

                except Exception as e:
                    logger.error(f"Tech — _process {company.get('site_web')} : {e}")
                    _state["errors"] += 1
                    return False

            with concurrent.futures.ThreadPoolExecutor(max_workers=parallel) as executor:
                futures = {
                    executor.submit(_process, c): c
                    for c in all_companies
                }
                for future in concurrent.futures.as_completed(futures):
                    if _state["accepted"] >= max_leads:
                        # Quota atteint — annuler les futures en attente
                        for f in futures:
                            f.cancel()
                        break
                    try:
                        accepted = future.result()
                        if accepted:
                            _state["accepted"] += 1
                        else:
                            _state["rejected"] += 1
                    except Exception as e:
                        _state["errors"] += 1
                        logger.error(f"Tech — future error : {e}")

            _log(
                f"TechScraper terminé — "
                f"{_state['accepted']} leads qualifiés, "
                f"{_state['rejected']} rejetés, "
                f"{_state['errors']} erreurs"
            )

            return {
                "accepted":    _state["accepted"],
                "rejected":    _state["rejected"],
                "errors":      _state["errors"],
                "campaign_id": campaign_id,
            }

        except Exception as e:
            logger.error(f"TechScraper erreur critique : {e}")
            _log(f"ERREUR CRITIQUE : {e}", "error")
            return {"error": str(e)}

        finally:
            _state["running"]  = False
            _state["phase"]    = "done"
            _state["ended_at"] = datetime.now().isoformat()
