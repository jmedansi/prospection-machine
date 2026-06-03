# -*- coding: utf-8 -*-
"""
scraper/sniper/jobs_scraper.py — Source 3 : Offres d'emploi France Travail

Lire scraper/sniper/JOBS_SCRAPER_README.md avant toute modification.

Signal de budget : une entreprise qui recrute un développeur, un responsable
e-commerce ou un chef de projet digital a un budget tech actif — elle paie
déjà pour cette infrastructure, donc elle peut payer pour l'optimiser.

Flux :
  Phase 1 → API France Travail (offres par mots-clés tech)
  Phase 2 → extraction domaine depuis l'offre
  Phase 3 → Wappalyzer  ← CMS détecté ? (filtre rapide)
  Phase 4 → PageSpeed   ← seulement si site non-auto-géré
  Phase 5 → scoring.py  ← tag_urgence + niveau_urgence
  Phase 6 → DB          ← INSERT leads_bruts source='jobs'

Usage programmatique :
    from scraper.sniper.jobs_scraper import JobsScraper
    s = JobsScraper()
    s.run(keywords=["développeur WordPress", "responsable e-commerce"], max_leads=50)
"""

import concurrent.futures
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ─── Constantes ──────────────────────────────────────────────────────────────

# API France Travail (ex Pôle Emploi) — v2, OAuth2 client_credentials
# Docs : https://francetravail.io/data/api/offres-emploi
_FT_TOKEN_URL  = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire"
_FT_OFFERS_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"

_REQUEST_TIMEOUT = 15
_INTER_REQUEST   = 0.4   # délai entre pages (quota API France Travail)

# Mots-clés qui signalent un budget tech/digital
DEFAULT_KEYWORDS = [
    "développeur WordPress",
    "développeur PrestaShop",
    "développeur e-commerce",
    "responsable e-commerce",
    "chef de projet digital",
    "développeur Shopify",
    "intégrateur web",
    "développeur full stack",
    "traffic manager",
    "responsable acquisition",
    "growth hacker",
    "développeur Magento",
]

# CMS auto-gérés — même liste que tech_scraper
_AUTOGEREE_CMS = {
    "Wix", "Squarespace", "Weebly", "Jimdo", "Webflow",
    "Blogger", "Tumblr", "GoDaddy Website Builder",
    "Strikingly", "Carrd", "Notion", "Site123",
}

# ─── État partagé ─────────────────────────────────────────────────────────────

_state: Dict = {
    "running":      False,
    "phase":        None,
    "total_offers": 0,
    "domains_done": 0,
    "accepted":     0,
    "rejected":     0,
    "errors":       0,
    "logs":         [],
    "started_at":   None,
    "ended_at":     None,
    "stop_requested": False,
}


def get_state() -> Dict:
    return dict(_state)


def reset_state() -> None:
    _state["running"] = False
    _state["phase"]   = None
    _state["stop_requested"] = False


def request_stop() -> None:
    """Demande l'arrêt propre du scraper."""
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


# ─── Auth France Travail ──────────────────────────────────────────────────────

_ft_token:    Optional[str]      = None
_ft_token_exp: Optional[datetime] = None


def _get_ft_token() -> Optional[str]:
    """
    Obtient un token OAuth2 France Travail (cache en mémoire, TTL 1490s).
    Nécessite FT_CLIENT_ID + FT_CLIENT_SECRET dans .env
    """
    global _ft_token, _ft_token_exp

    if _ft_token and _ft_token_exp and datetime.now() < _ft_token_exp:
        return _ft_token

    client_id     = os.getenv("FT_CLIENT_ID")
    client_secret = os.getenv("FT_CLIENT_SECRET")

    if not client_id or not client_secret:
        logger.warning(
            "FT_CLIENT_ID / FT_CLIENT_SECRET manquants dans .env — "
            "Source 3 (Jobs) désactivée"
        )
        return None

    try:
        resp = requests.post(
            _FT_TOKEN_URL,
            data={
                "grant_type":    "client_credentials",
                "client_id":     client_id,
                "client_secret": client_secret,
                "scope":         "api_offresdemploiv2 o2dsoffre",
            },
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"France Travail auth échouée : {e}")
        return None

    _ft_token     = data.get("access_token")
    expires_in    = int(data.get("expires_in", 1499))
    _ft_token_exp = datetime.now() + timedelta(seconds=expires_in - 10)
    return _ft_token


# ─── Phase 1 : Fetch offres France Travail ────────────────────────────────────

def _fetch_offers(keyword: str, max_offers: int, days_back: int = 7) -> list[dict]:
    """
    Recherche des offres d'emploi pour un mot-clé.
    Retourne une liste de dicts offre bruts France Travail.
    """
    token = _get_ft_token()
    if not token:
        return []

    results = []
    start   = 0

    # Date min de publication (offres récentes = entreprises en croissance)
    date_min = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%dT00:00:00Z")

    while len(results) < max_offers:
        try:
            resp = requests.get(
                _FT_OFFERS_URL,
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "motsCles":        keyword,
                    "minCreationDate": date_min,
                    "maxCreationDate": datetime.now().strftime("%Y-%m-%dT23:59:59Z"),
                    "range":           f"{start}-{min(start + 149, start + max_offers - len(results) - 1)}",
                    "sort":            "1",   # tri par date
                },
                timeout=_REQUEST_TIMEOUT,
            )

            if resp.status_code == 204:
                # Aucun résultat pour ce mot-clé
                break
            resp.raise_for_status()
            data = resp.json()

        except Exception as e:
            logger.warning(f"France Travail fetch '{keyword}' start={start} : {e}")
            break

        batch = data.get("resultats") or []
        results.extend(batch)

        content_range = resp.headers.get("Content-Range", "")
        # "offres 0-149/1204" → total = 1204
        m = re.search(r"/(\d+)$", content_range)
        total = int(m.group(1)) if m else len(results)

        start += len(batch)
        if start >= total or not batch:
            break

        time.sleep(_INTER_REQUEST)

    return results[:max_offers]


# ─── Phase 2 : Extraction domaine depuis une offre ───────────────────────────

def _extract_domain(offer: dict) -> Optional[str]:
    """
    Extrait le site web de l'entreprise depuis une offre France Travail.
    Stratégie :
      1. entreprise.url (rarement présent dans l'API)
      2. contact.urlPostulation → retirer /jobs/... pour garder le domaine
      3. Reconstruit depuis entreprise.nom si c'est un domaine évident
    """
    entreprise = offer.get("entreprise") or {}

    # 1. URL directe de l'entreprise
    url = entreprise.get("url") or ""
    if url:
        return _normalize_url(url)

    # 2. URL de candidature → extrait le domaine racine
    contact = offer.get("contact") or {}
    url_postulation = contact.get("urlPostulation") or ""
    if url_postulation:
        parsed = urlparse(url_postulation)
        if parsed.netloc and "francetravail" not in parsed.netloc.lower():
            return f"{parsed.scheme}://{parsed.netloc}"

    return None


def _normalize_url(url: str) -> str:
    """Normalise une URL : force https://, supprime chemin."""
    url = url.strip().rstrip("/")
    if not url.startswith("http"):
        url = "https://" + url
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


# ─── Phase 3-4 : Wappalyzer + PageSpeed ──────────────────────────────────────

def _run_wappalyzer(site_web: str) -> dict:
    try:
        from scraper.sniper.wappalyzer_runner import analyze
        return analyze(site_web, timeout=30)
    except Exception as e:
        logger.debug(f"Wappalyzer {site_web} : {e}")
        return {"cms": None, "cdn": None, "ecommerce": None,
                "server": None, "technologies": [], "error": str(e)}


def _run_pagespeed(site_web: str) -> dict:
    try:
        from auditeur.agents.web_analyzer import run_pagespeed
        return run_pagespeed(site_web, "mobile") or {}
    except Exception as e:
        logger.debug(f"PageSpeed {site_web} : {e}")
        return {}


# ─── Phase 5-6 : Scoring → DB ────────────────────────────────────────────────

def _score_and_store(site_web: str, offer: dict, wap: dict, pagespeed: dict) -> bool:
    """Applique le scoring et insère le lead qualifié."""
    from scraper.sniper.scoring import score_lead, build_donnees_audit
    from database import insert_lead, get_conn

    result = score_lead(pagespeed, wap, source="jobs")
    if result is None:
        return False

    tag, niveau, reason = result

    entreprise  = offer.get("entreprise") or {}
    company_name = entreprise.get("nom") or urlparse(site_web).netloc.lstrip("www.")
    lieu         = (offer.get("lieuTravail") or {}).get("libelle") or ""
    rome_code    = (offer.get("romeCode") or "")
    keyword_used = offer.get("_keyword_used", "")

    donnees_dict = json.loads(build_donnees_audit(pagespeed, wap, tag, niveau, reason))
    donnees_dict["keyword_signal"] = keyword_used
    donnees_dict["rome_code"]      = rome_code
    donnees_dict["offer_id"]       = offer.get("id", "")
    donnees = json.dumps(donnees_dict, ensure_ascii=False)

    # Déduplication sur site_web
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM leads_bruts WHERE site_web=? AND source='jobs' "
            "AND statut NOT IN ('archive','desabonne')",
            (site_web,)
        ).fetchone()
        if existing:
            logger.debug(f"Jobs — {site_web} déjà présent, ignoré")
            return False

    lead_id = insert_lead({
        "nom":            company_name,
        "adresse":        "",
        "ville":          lieu,
        "site_web":       site_web,
        "telephone":      "",
        "email":          "",
        "mot_cle":        keyword_used,
        "category":       f"Signal RH — {keyword_used}",
        "source":         "jobs",
        "tag_urgence":    tag,
        "niveau_urgence": niveau,
        "donnees_audit":  donnees,
        "statut":         "en_attente",
    })

    if lead_id:
        cms = wap.get("cms") or wap.get("ecommerce") or "full-code"
        _log(f"  ✓  {site_web} — {tag} niv.{niveau} | {cms} | signal: {keyword_used}")
        return True

    return False


# ─── Orchestrateur ────────────────────────────────────────────────────────────

class JobsScraper:
    """
    Scraper Source 3 — offres d'emploi tech = signal de budget digital.

    Usage :
        s = JobsScraper()
        s.run(keywords=["développeur WordPress"], max_offers_per_kw=50, max_leads=30)
    """

    def run(
        self,
        keywords:          Optional[List[str]] = None,
        max_offers_per_kw: int = 50,
        days_back:         int = 7,
        max_leads:         int = 50,
        parallel:          int = 3,
        campaign_name:     Optional[str] = None,
    ) -> Dict:
        """
        Exécute le pipeline jobs complet.

        Args:
            keywords:          mots-clés de recherche RH (défaut : DEFAULT_KEYWORDS)
            max_offers_per_kw: max offres à récupérer par mot-clé
            days_back:         n'examiner que les offres des N derniers jours
            max_leads:         limite d'insertions en base
            parallel:          threads pour Wap + PageSpeed
            campaign_name:     nom de la campagne DB

        Returns:
            {"accepted": int, "rejected": int, "errors": int, "campaign_id": int}
        """
        if _state["running"]:
            return {"error": "JobsScraper déjà en cours"}

        _state.update({
            "running": True, "phase": "fetch",
            "total_offers": 0, "domains_done": 0,
            "accepted": 0, "rejected": 0, "errors": 0,
            "stop_requested": False,  # Réinitialisation cruciale
            "logs": [], "started_at": datetime.now().isoformat(), "ended_at": None,
        })

        if keywords is None:
            keywords = DEFAULT_KEYWORDS

        try:
            # ── Créer la campagne ─────────────────────────────────────────────
            from database import insert_campaign
            if not campaign_name:
                campaign_name = f"Sniper Jobs — {datetime.now().strftime('%d/%m %H:%M')}"
            campaign_id = insert_campaign(campaign_name, "jobs", "fr")
            _log(f"Campagne créée : #{campaign_id} — {campaign_name}")

            # ── Phase 1 : Fetch France Travail ────────────────────────────────
            _state["phase"] = "fetch"
            _log(f"Phase 1 — France Travail ({len(keywords)} mots-clés, {days_back}j)")

            # Collecte et déduplication des domaines
            domain_map: Dict[str, dict] = {}   # site_web → offer

            for kw in keywords:
                offers = _fetch_offers(kw, max_offers_per_kw, days_back)
                _log(f"  '{kw}' → {len(offers)} offres")

                for offer in offers:
                    offer["_keyword_used"] = kw
                    site_web = _extract_domain(offer)
                    if not site_web:
                        continue
                    # Garder une offre par domaine (la plus récente / premier trouvé)
                    if site_web not in domain_map:
                        domain_map[site_web] = offer

            _state["total_offers"] = len(domain_map)
            _log(f"  {len(domain_map)} domaines uniques extraits")

            if not domain_map:
                _log(
                    "Aucun domaine extrait — vérifier FT_CLIENT_ID/FT_CLIENT_SECRET "
                    "et les mots-clés"
                )
                return {"accepted": 0, "rejected": 0, "errors": 0, "campaign_id": campaign_id}

            # ── Phase 2+3+4+5 : Wap → PageSpeed → Scoring → DB (parallèle) ──
            _state["phase"] = "enrichissement"
            _log(f"Phase 2 — Wappalyzer + scoring ({parallel} threads, max {max_leads} leads)")

            def _process(item: tuple[str, dict]) -> bool:
                site_web, offer = item
                try:
                    wap = _run_wappalyzer(site_web)
                    _state["domains_done"] += 1

                    # Rejeter seulement les CMS auto-gérés
                    cms = wap.get("cms") or wap.get("ecommerce")
                    if cms and cms in _AUTOGEREE_CMS:
                        return False

                    pagespeed = _run_pagespeed(site_web)
                    return _score_and_store(site_web, offer, wap, pagespeed)

                except Exception as e:
                    logger.error(f"Jobs — _process {site_web} : {e}")
                    _state["errors"] += 1
                    return False
                finally:
                    try:
                        from core.browser import cleanup_sync_thread
                        cleanup_sync_thread()
                    except Exception:
                        pass

            with concurrent.futures.ThreadPoolExecutor(max_workers=parallel) as executor:
                futures = {
                    executor.submit(_process, item): item
                    for item in domain_map.items()
                }
                for future in concurrent.futures.as_completed(futures):
                    if _state["accepted"] >= max_leads:
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
                        logger.error(f"Jobs — future error : {e}")

            _log(
                f"JobsScraper terminé — "
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
            logger.error(f"JobsScraper erreur critique : {e}")
            _log(f"ERREUR CRITIQUE : {e}", "error")
            return {"error": str(e)}

        finally:
            _state["running"]  = False
            _state["phase"]    = "done"
            _state["ended_at"] = datetime.now().isoformat()
