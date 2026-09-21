# -*- coding: utf-8 -*-
"""
scraper/sniper/transparency_pipeline.py — Pipeline Google Ads Transparency Center

Flux :
  Phase 1   → transparency_extractor : mots-clés → annonceurs Google actifs
  Phase 1.5 → enrichissement : contact_finder + ceo_finder + smtp_validator
  Phase 2   → PageSpeed + Wappalyzer
  Phase 3   → scoring + insert leads_bruts (source='transparency')

État partagé pollable via get_transparency_state().
"""

import concurrent.futures
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ─── État partagé ─────────────────────────────────────────────────────────────

_state: Dict = {
    "running":    False,
    "phase":      None,
    "total":      0,
    "processed":  0,
    "accepted":   0,
    "rejected":   0,
    "errors":     0,
    "logs":       [],
    "started_at": None,
    "ended_at":   None,
    "stop_requested": False,
}


def get_state() -> Dict:
    return dict(_state)


def reset_state() -> None:
    _state["running"] = False
    _state["phase"]   = None
    _state["stop_requested"] = False


def request_stop() -> None:
    """Demande l'arrêt du pipeline."""
    _state["stop_requested"] = True
    _log("🛑 Arrêt demandé par l'utilisateur", level="warning")


def is_stop_requested() -> bool:
    """Vérifie si un arrêt a été demandé."""
    return _state.get("stop_requested", False)


def _log(msg: str, level: str = "info"):
    getattr(logger, level)(msg)
    _state["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    if len(_state["logs"]) > 50:
        _state["logs"].pop(0)


# ─── Phase 2 : Enrichissement d'un domaine ────────────────────────────────────

def _enrich_domain(domain_info: Dict) -> Optional[Dict]:
    """Enrichit un domaine avec PageSpeed + Wappalyzer."""
    url = domain_info["domaine"]
    try:
        from auditeur.agents.web_analyzer import run_pagespeed
        from scraper.sniper.wappalyzer_runner import analyze as wappalyzer_analyze

        pagespeed_result = {}
        wappalyzer_result = {}

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_ps = executor.submit(run_pagespeed, url, "mobile")
            future_wa = executor.submit(wappalyzer_analyze, url)
            try:
                pagespeed_result = future_ps.result(timeout=90)
            except Exception as e:
                logger.warning(f"PageSpeed échoué pour {url}: {e}")
            try:
                wappalyzer_result = future_wa.result(timeout=45)
            except Exception as e:
                logger.warning(f"Wappalyzer échoué pour {url}: {e}")

        return {**domain_info, "pagespeed": pagespeed_result, "wappalyzer": wappalyzer_result}
    except Exception as e:
        logger.error(f"Enrichissement échoué pour {url}: {e}")
        return None


# ─── Phase 3 : Scoring → DB ───────────────────────────────────────────────────

def _score_and_store(enriched: Dict, campaign_id: int) -> bool:
    """Applique le scoring et insère le lead qualifié en base."""
    from scraper.sniper.scoring import score_lead, build_donnees_audit
    from urllib.parse import urlparse

    url       = enriched["domaine"]
    mot_cle   = enriched.get("mot_cle", "")
    pays      = enriched.get("pays", "FR")
    pagespeed = enriched.get("pagespeed", {})
    wap       = enriched.get("wappalyzer", {})

    result = score_lead(pagespeed, wap, source="ads")
    if result is None:
        _log(f"  ✗  {url} — rejeté")
        return False

    tag, niveau, reason = result
    donnees_json = build_donnees_audit(pagespeed, wap, tag, niveau, reason)

    parsed       = urlparse(url)
    netloc       = parsed.netloc.lower().lstrip("www.")
    company_name = (
        enriched.get("advertiser_name")
        or netloc.split(".")[0].replace("-", " ").title()
    )

    email     = enriched.get("email_valide") or enriched.get("email_contact") or ""
    telephone = enriched.get("telephone") or ""
    ceo_nom_complet = " ".join(filter(None, [
        enriched.get("ceo_prenom"), enriched.get("ceo_nom")
    ])) or company_name

    from database import insert_lead
    lead_id = insert_lead({
        "campaign_id":    campaign_id,
        "nom":            ceo_nom_complet,
        "adresse":        "",
        "ville":          pays.upper(),
        "site_web":       url,
        "telephone":      telephone,
        "email":          email,
        "mot_cle":        mot_cle,
        "category":       f"Annonceur Google — {mot_cle}",
        "source":         "transparency",
        "tag_urgence":    tag,
        "niveau_urgence": niveau,
        "donnees_audit":  donnees_json,
        "statut":         "en_attente",
    })

    if lead_id:
        _log(f"  ✓  {url} — {tag} niveau {niveau} | {reason}")
        return True
    return False


# ─── Pipeline principal ────────────────────────────────────────────────────────

class TransparencyPipeline:
    """
    Pipeline Sniper — Source Google Ads Transparency Center.

    Usage :
        pipeline = TransparencyPipeline()
        pipeline.run(
            keywords=["serrurier paris", "agence web lyon"],
            country="FR",
            max_per_kw=20,
        )
    """

    def run(
        self,
        keywords:        List[str],
        country:         str = "FR",
        max_per_kw:      int = 20,
        parallel_enrich: int = 3,
        campaign_name:   Optional[str] = None,
    ) -> Dict:
        if _state["running"]:
            return {"error": "Pipeline déjà en cours"}

        _state.update({
            "running": True, "phase": "extraction",
            "total": 0, "processed": 0, "accepted": 0, "rejected": 0, "errors": 0,
            "stop_requested": False,  # Réinitialisation cruciale
            "logs": [], "started_at": datetime.now().isoformat(), "ended_at": None,
        })

        try:
            from database import insert_campaign
            if not campaign_name:
                campaign_name = (
                    f"Sniper Transparency — {country.upper()} "
                    f"— {datetime.now().strftime('%d/%m %H:%M')}"
                )
            campaign_id = insert_campaign(
                campaign_name, "transparency", country,
                nb_demande=len(keywords) * max_per_kw
            )
            _log(f"Campagne créée : #{campaign_id} — {campaign_name}")

            # ── Phase 1 : Extraction ──────────────────────────────────────────
            _state["phase"] = "extraction"
            _log(f"Phase 1 — Ads Transparency ({len(keywords)} mots-clés, pays={country})")

            from scraper.sniper.transparency_extractor import extract_transparency_ads
            raw_leads = extract_transparency_ads(keywords, country=country, max_per_kw=max_per_kw)

            _state["total"] = len(raw_leads)
            _log(f"  {len(raw_leads)} annonceurs extraits")

            if not raw_leads:
                _log("Aucun annonceur trouvé — vérifier les mots-clés ou la connexion")
                return {"accepted": 0, "rejected": 0, "errors": 0, "campaign_id": campaign_id}

            # ── Phase 1.5 : Enrichissement contact + CEO ─────────────────────
            _state["phase"] = "enrichissement_contact"
            _log(f"Phase 1.5 — Enrichissement contact ({len(raw_leads)} leads)")

            from core.contact_finder import find_contacts
            from urllib.parse import urlparse as _urlparse

            for lead in raw_leads:
                url     = lead.get("domaine", "")
                _parsed = _urlparse(url)
                domain  = _parsed.netloc.lstrip("www.") or url
                company = lead.get("advertiser_name") or domain.split(".")[0].replace("-", " ").title()

                try:
                    lead.update(find_contacts(url, company, pays=lead.get("pays", "fr")))
                except Exception as e:
                    logger.warning(f"contact_finder échoué pour {url}: {e}")

                _log(
                    f"  ✉  {url} — "
                    f"email={lead.get('email_valide','?')} "
                    f"CEO={lead.get('ceo_prenom','?')} {lead.get('ceo_nom','?')}"
                )

            # ── Phase 2 : PageSpeed + Wappalyzer ─────────────────────────────
            _state["phase"] = "enrichissement"
            _log(f"Phase 2 — PageSpeed + Wappalyzer ({parallel_enrich} threads)")

            enriched_leads = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=parallel_enrich) as executor:
                futures = {executor.submit(_enrich_domain, lead): lead for lead in raw_leads}
                for future in concurrent.futures.as_completed(futures):
                    _state["processed"] += 1
                    try:
                        result = future.result()
                        if result:
                            enriched_leads.append(result)
                        else:
                            _state["errors"] += 1
                    except Exception as e:
                        _state["errors"] += 1
                        logger.error(f"Thread error: {e}")

            _log(f"  {len(enriched_leads)}/{len(raw_leads)} domaines enrichis")

            # ── Phase 3 : Scoring → DB ────────────────────────────────────────
            _state["phase"] = "scoring"
            _log(f"Phase 3 — Scoring ({len(enriched_leads)} candidats)")

            for enriched in enriched_leads:
                try:
                    if _score_and_store(enriched, campaign_id):
                        _state["accepted"] += 1
                    else:
                        _state["rejected"] += 1
                except Exception as e:
                    _state["errors"] += 1
                    logger.error(f"Score/store error: {e}")

            _log(
                f"Pipeline terminé — "
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
            logger.error(f"Pipeline Transparency erreur critique: {e}")
            _log(f"ERREUR CRITIQUE : {e}", "error")
            return {"error": str(e)}

        finally:
            _state["running"]  = False
            _state["phase"]    = "done"
            _state["ended_at"] = datetime.now().isoformat()
