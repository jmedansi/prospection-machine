# -*- coding: utf-8 -*-
"""
sniper/enrichment/pre_filter.py — Pré-filtre léger (~3s/site)

Lire sniper/enrichment/README.md avant toute modification.

Responsabilité :
  - Mesurer le TTFB (Time To First Byte)
  - Détecter la présence/absence de GTM et GA
  - Détecter les grosses marques (à rejeter)
  - Calculer le score de chaleur (0-12)
  - Rejeter les leads sous le seuil avant d'appeler PageSpeed

NE lance PAS PageSpeed. NE lance PAS Playwright.
Utilise uniquement requests + stream (lecture des 80 premiers Ko).
"""

import time
import logging

import requests

logger = logging.getLogger(__name__)

# ── Grosses marques à rejeter immédiatement ────────────────────────────────────
_BRAND_BLACKLIST = {
    "amazon", "fnac", "darty", "leroy-merlin", "leroymerlin",
    "castorama", "boulanger", "cdiscount", "laredoute", "ldlc",
    "orange", "sfr", "bouygues", "free", "sncf", "edf", "engie",
    "carrefour", "intermarche", "leclerc", "auchan", "lidl", "aldi",
    "decathlon", "ikea", "bricorama", "manomano", "veepee", "showroomprive",
}

# ── Score de chaleur ───────────────────────────────────────────────────────────
_SCORE_NO_GTM    = 4   # Absence GTM/GA = enjeu ROI fort
_SCORE_SLOW_TTFB = 2   # TTFB > 500ms = serveur lent
_SCORE_VERY_SLOW = 1   # TTFB > 1500ms (bonus)
_SCORE_PENALTY   = -10 # Grosse marque → rejet direct

MIN_HEAT_SCORE = 3     # Seuil minimum pour passer en Phase 2


from core.domain import normalize_url as _normalize_url, extract_domain as _extract_domain


def _is_big_brand(domain: str) -> bool:
    base = domain.split(".")[0]
    return base in _BRAND_BLACKLIST


def pre_filter(url: str, timeout: int = 5) -> dict:
    """
    Analyse légère d'un domaine annonceur.

    Args:
        url:     URL du site (avec ou sans https://)
        timeout: Timeout en secondes (défaut 5)

    Returns:
        {
            "reachable":   bool,
            "ttfb_ms":     int,
            "has_gtm":     bool,
            "has_ga":      bool,
            "is_big_brand": bool,
            "heat_score":  int,   # 0-12
            "keep":        bool,  # False = rejeter avant PageSpeed
        }
    """
    url    = _normalize_url(url)
    domain = _extract_domain(url)

    result = {
        "reachable":    False,
        "ttfb_ms":      9999,
        "has_gtm":      False,
        "has_ga":       False,
        "is_big_brand": False,
        "heat_score":   0,
        "keep":         False,
    }

    # ── Rejet immédiat — grosse marque ────────────────────────────────────────
    if _is_big_brand(domain):
        result["is_big_brand"] = True
        result["heat_score"]   = _SCORE_PENALTY
        logger.debug(f"pre_filter: grosse marque rejetée — {domain}")
        return result

    # ── Requête HTTP légère en streaming ─────────────────────────────────────
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; audit-bot/1.0)"}
        t0   = time.time()
        resp = requests.get(url, headers=headers, timeout=timeout, stream=True)
        result["ttfb_ms"]   = int((time.time() - t0) * 1000)
        result["reachable"] = True

        # Lire seulement les 80 premiers Ko (suffisant pour le <head>)
        chunk = b""
        for part in resp.iter_content(chunk_size=8192):
            chunk += part
            if len(chunk) >= 80_000:
                break

        html = chunk.decode("utf-8", errors="ignore").lower()

        result["has_gtm"] = "googletagmanager.com" in html or "gtm.js" in html
        result["has_ga"]  = (
            "google-analytics.com" in html
            or "gtag(" in html
            or "ga.js" in html
            or "analytics.js" in html
        )

    except requests.exceptions.Timeout:
        result["ttfb_ms"] = timeout * 1000
        result["reachable"] = False
        logger.debug(f"pre_filter: timeout sur {url}")
    except Exception as e:
        logger.debug(f"pre_filter: erreur {url} — {e}")
        return result

    # ── Calcul du score de chaleur ─────────────────────────────────────────────
    score = 0

    # Absence de tracking = ils dépensent en pub sans mesurer → argument fort
    if not result["has_gtm"] and not result["has_ga"]:
        score += _SCORE_NO_GTM

    # Serveur lent = problème de perf confirmé avant même PageSpeed
    if result["ttfb_ms"] > 1500:
        score += _SCORE_SLOW_TTFB + _SCORE_VERY_SLOW
    elif result["ttfb_ms"] > 500:
        score += _SCORE_SLOW_TTFB

    # Site injoignable = signal négatif (pas de lead valide)
    if not result["reachable"]:
        score = 0

    result["heat_score"] = score
    result["keep"]       = score >= MIN_HEAT_SCORE

    logger.debug(
        f"pre_filter: {domain} — ttfb={result['ttfb_ms']}ms "
        f"gtm={result['has_gtm']} score={score} keep={result['keep']}"
    )
    return result


def filter_batch(domains: list[dict], top_n: int = 30, min_score: int = MIN_HEAT_SCORE) -> list[dict]:
    """
    Pré-filtre une liste de leads et retourne les top_n par score de chaleur.

    Args:
        domains: Liste de dicts avec au moins {"domaine": "https://..."}
        top_n:   Nombre maximum de leads à garder pour le PageSpeed

    Returns:
        Liste triée par heat_score décroissant, limitée à top_n
    """
    results = []
    for lead in domains:
        url = lead.get("domaine") or lead.get("site_web") or ""
        if not url:
            continue
        pf = pre_filter(url)
        lead_enriched = {**lead, **pf}
        results.append(lead_enriched)
        status = "KEEP" if pf["keep"] else "SKIP"
        logger.info(
            f"[pre_filter] {status} {url} — "
            f"score={pf['heat_score']} ttfb={pf['ttfb_ms']}ms "
            f"gtm={pf['has_gtm']}"
        )

    kept    = [r for r in results if r["heat_score"] >= min_score and r["reachable"]]
    skipped = [r for r in results if not r["keep"]]

    logger.info(
        f"filter_batch: {len(kept)}/{len(results)} gardés "
        f"({len(skipped)} rejetés) → top {top_n}"
    )

    kept.sort(key=lambda x: x["heat_score"], reverse=True)
    return kept[:top_n]
