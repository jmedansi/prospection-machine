# -*- coding: utf-8 -*-
"""
scraper/sniper/scoring.py — Phase 3 : Moteur de scoring High-Ticket

Règles appliquées sur les données enrichies (PageSpeed + Wappalyzer) :

REJET  → lead détruit, ne passe pas en base
VALIDE → lead accepté avec tag_urgence + niveau_urgence (1-5)

Logique de tags :
  "perf"          → site lent, ROAS négatif sur les pubs
  "securite"      → CMS vulnérable sans CDN/WAF
  "perf+securite" → cumulatif (niveau max)
"""

import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ─── CMS considérés comme "sans budget technique" (à rejeter) ─────────────────

_REJECT_CMS = {
    "Wix", "Squarespace", "Weebly", "Jimdo", "Webflow",
    "Blogger", "Tumblr",
}

# ─── CMS vulnérables et mal optimisés (cible haute valeur) ────────────────────

_HIGH_VALUE_CMS = {
    "WordPress", "WooCommerce", "PrestaShop", "Magento",
    "Joomla", "Drupal", "OpenCart",
}

# ─── Seuils PageSpeed ──────────────────────────────────────────────────────────

_SCORE_REJECT    = 85   # > 85 : le site est bien optimisé, pas besoin de nous
_SCORE_URGENT_5  = 30   # < 30 : urgence maximale
_SCORE_URGENT_4  = 50   # < 50 : très urgent
_SCORE_URGENT_3  = 65   # < 65 : urgent
_SCORE_URGENT_2  = 75   # < 75 : moyen

_FCP_ALERT_MS    = 2500  # > 2.5s FCP = problème UX visible
_FCP_CRITICAL_MS = 4000  # > 4s  FCP = catastrophique


def score_lead(
    pagespeed: Dict,
    wappalyzer: Dict,
    source: str = "ads",
) -> Optional[Tuple[str, int, str]]:
    """
    Applique les règles de qualification high-ticket.

    Args:
        pagespeed:  résultat de run_pagespeed() — {mobile_score, fcp_ms, ...}
        wappalyzer: résultat de wappalyzer_runner.analyze() — {cms, cdn, ...}
        source:     'ads' | 'tech' | 'jobs'

    Returns:
        (tag_urgence, niveau_urgence, reason) si le lead est qualifié
        None si le lead doit être rejeté

    Exemples de retour :
        ("perf",            5, "Score mobile 22/100 — ROAS négatif garanti")
        ("securite",        4, "PrestaShop sans Cloudflare")
        ("perf+securite",   5, "Score 28 + WooCommerce nu")
        None                   → rejeté
    """
    mobile_score = pagespeed.get("mobile_score")
    # FCP = First Contentful Paint (premier pixel) — seuils 2.5s/4s
    # LCP = Largest Contentful Paint (contenu principal) — toujours > FCP
    # On utilise FCP mobile pour les seuils d'alerte ; LCP pour le message prospect
    fcp_ms       = pagespeed.get("mobile_fcp_ms") or pagespeed.get("fcp_ms")
    lcp_ms       = pagespeed.get("mobile_lcp_ms")
    cms          = wappalyzer.get("cms")
    cdn          = wappalyzer.get("cdn")
    ecommerce    = wappalyzer.get("ecommerce")
    has_cdn      = cdn is not None

    # ── Règles de REJET ──────────────────────────────────────────────────────

    # 1. CMS low-code = pas de budget tech
    if cms and cms in _REJECT_CMS:
        logger.debug(f"  REJET — CMS low-code : {cms}")
        return None

    # 2. Score excellent = pas besoin de nous
    if mobile_score is not None and mobile_score > _SCORE_REJECT:
        logger.debug(f"  REJET — Score mobile trop bon : {mobile_score}")
        return None

    # ── Calcul du niveau d'urgence ───────────────────────────────────────────

    urgence_perf     = 0
    urgence_secu     = 0
    reasons_perf     = []
    reasons_secu     = []

    # Priorité argumentaire e-commerce (du plus fort au plus faible) :
    # 1. Budget pub gaspillé (visiteur payant qui repart sans acheter)
    # 2. Panier abandonné (intention d'achat = CA direct perdu)
    # 3. Bots de carding / fraude (perte financière immédiate)
    # 4. -7% conversion/seconde (chiffrable sur leur CA actuel)
    # 5. Google Shopping pénalisé (moins de trafic = moins de ventes)
    is_ecom = source == "ecom" or (ecommerce is not None)

    if mobile_score is not None:
        if mobile_score < _SCORE_URGENT_5:
            urgence_perf = 5
            # Budget pub + conversion loss cumulés — argument maximal
            msg = (f"Score mobile {int(mobile_score)}/100 — vos visiteurs payants repartent sans acheter"
                   f" (-7% de CA par seconde de latence)") if is_ecom else f"Score mobile {int(mobile_score)}/100 — catastrophique"
            reasons_perf.append(msg)
        elif mobile_score < _SCORE_URGENT_4:
            urgence_perf = 4
            # Panier abandonné = intention d'achat = argument le plus concret
            msg = (f"Score mobile {int(mobile_score)}/100 — paniers abandonnés en cours de commande,"
                   f" CA perdu chaque jour") if is_ecom else f"Score mobile {int(mobile_score)}/100 — tres lent"
            reasons_perf.append(msg)
        elif mobile_score < _SCORE_URGENT_3:
            urgence_perf = 3
            # Google Shopping = trafic et donc CA
            msg = (f"Score mobile {int(mobile_score)}/100 — penalise Google Shopping,"
                   f" moins d'impressions = moins de ventes") if is_ecom else f"Score mobile {int(mobile_score)}/100 — lent"
            reasons_perf.append(msg)
        elif mobile_score < _SCORE_URGENT_2:
            urgence_perf = 2
            reasons_perf.append(f"Score mobile {int(mobile_score)}/100")
    elif pagespeed.get("pagespeed_error"):
        # Erreur technique PageSpeed (timeout, block, etc.)
        # On ne rejette pas forcément (le lead peut être bon), mais on marque l'urgence comme faible/inconnue
        urgence_perf = 1
        reasons_perf.append(f"Audit performance indisponible ({pagespeed.get('pagespeed_error')})")

    # FCP détermine le niveau d'urgence ; LCP est cité (métrique visible par le prospect)
    if fcp_ms and fcp_ms > _FCP_CRITICAL_MS:
        urgence_perf = max(urgence_perf, 4)
        # Afficher LCP si dispo (plus parlant), sinon FCP avec son vrai label
        if lcp_ms:
            display_s, metric = f"{lcp_ms/1000:.1f}", "LCP"
        else:
            display_s, metric = f"{fcp_ms/1000:.1f}", "FCP"
        msg = (f"{metric} {display_s}s — le visiteur repart avant de voir vos produits"
               f" (budget ads gaspille)") if is_ecom else f"{metric} {display_s}s sur mobile — page invisible pendant {display_s}s"
        reasons_perf.append(msg)
    elif fcp_ms and fcp_ms > _FCP_ALERT_MS:
        urgence_perf = max(urgence_perf, 3)
        if lcp_ms:
            display_s, metric = f"{lcp_ms/1000:.1f}", "LCP"
        else:
            display_s, metric = f"{fcp_ms/1000:.1f}", "FCP"
        msg = (f"{metric} {display_s}s — taux de rebond catalogue eleve,"
               f" retour sur ads negatif") if is_ecom else f"{metric} {display_s}s sur mobile — experience degradee"
        reasons_perf.append(msg)

    # Urgence SÉCURITÉ / INFRASTRUCTURE
    effective_cms = cms or ecommerce
    if effective_cms and effective_cms in _HIGH_VALUE_CMS:
        if not has_cdn:
            urgence_secu = 4
            # Fraude directe = argument financier immédiat
            msg = (f"{effective_cms} sans CDN/WAF — bots de carding (fraude CB),"
                   f" scraping des prix, risque DDoS en periode de soldes") if is_ecom else f"{effective_cms} sans CDN/WAF — exposition totale aux bots et DDoS"
            reasons_secu.append(msg)
        elif mobile_score and mobile_score < _SCORE_URGENT_4:
            urgence_secu = 2
            reasons_secu.append(f"{effective_cms} avec CDN mais non optimise — performances insuffisantes")

    # ── Décision finale ──────────────────────────────────────────────────────
    niveau = max(urgence_perf, urgence_secu)

    if niveau == 0:
        if mobile_score is None:
            # Audit technique en échec (ex: API key manquante)
            logger.debug("  QUALIFIÉ PAR DÉFAUT (Audit échoué) — niveau 1")
            return "audit_pending", 1, "Audit technique en attente ou échoué"
        
        logger.debug("  REJET — aucun signal d'urgence")
        return None

    # Détermination du tag
    has_perf = urgence_perf >= 2
    has_secu = urgence_secu >= 2

    if has_perf and has_secu:
        tag = "perf+securite"
    elif has_secu:
        tag = "securite"
    else:
        tag = "perf"

    # Bonus +1 si cumulatif
    if has_perf and has_secu:
        niveau = min(5, niveau + 1)

    all_reasons = reasons_perf + reasons_secu
    reason = " | ".join(all_reasons) if all_reasons else f"Urgence niveau {niveau}"

    logger.debug(f"  QUALIFIÉ — tag={tag} niveau={niveau} : {reason}")
    return tag, niveau, reason


def build_donnees_audit(
    pagespeed: Dict,
    wappalyzer: Dict,
    tag: str,
    niveau: int,
    reason: str,
    enriched: Optional[Dict] = None,
) -> str:
    """Sérialise les données de pré-qualification en JSON pour donnees_audit."""
    import json
    enriched = enriched or {}

    # Score SEO réel depuis PageSpeed Insights (mobile ou desktop)
    # Priorité : mobile_seo_score > desktop_seo_score > fallback calculé
    score_seo_real = pagespeed.get("mobile_seo_score") or pagespeed.get("score_seo")
    if not score_seo_real:
        score_seo_real = pagespeed.get("desktop_seo_score")
    
    if score_seo_real:
        score_seo = score_seo_real
    else:
        # Fallback : calcul basé sur Wappalyzer si PageSpeed ne fournit pas de score SEO
        seo_flags = []
        if wappalyzer.get("has_https") or enriched.get("has_https"):
            seo_flags.append(True)
        if wappalyzer.get("cdn") or enriched.get("has_cdn"):
            seo_flags.append(True)
        cms = wappalyzer.get("cms") or wappalyzer.get("ecommerce")
        if cms and cms in _HIGH_VALUE_CMS:
            seo_flags.append(True)
        techs = wappalyzer.get("technologies", [])
        modern_tech = any(t in str(techs).lower() for t in ["analytics", "gtm", "google tag", "facebook pixel"])
        if modern_tech:
            seo_flags.append(True)
        score_seo = round((len(seo_flags) / 4) * 100) if seo_flags else 50

    # Autres scores PageSpeed (accessibility, best-practices)
    score_accessibility = pagespeed.get("mobile_accessibility_score") or pagespeed.get("score_accessibility")
    score_best_practices = pagespeed.get("mobile_best_practices_score") or pagespeed.get("score_best_practices")

    return json.dumps({
        "score_mobile":      pagespeed.get("mobile_score"),
        "score_desktop":     pagespeed.get("desktop_score"),
        "score_seo":         score_seo,
        "score_accessibility": score_accessibility,
        "score_best_practices": score_best_practices,
        "fcp_ms":            pagespeed.get("fcp_ms"),
        "lcp_ms":            pagespeed.get("mobile_lcp_ms"),
        "cms":               wappalyzer.get("cms"),
        "cdn":               wappalyzer.get("cdn"),
        "ecommerce":         wappalyzer.get("ecommerce"),
        "server":            wappalyzer.get("server"),
        "technologies":      wappalyzer.get("technologies", []),
        "tag":               tag,
        "niveau":            niveau,
        "reason":            reason,
        # Enrichissement CEO + email (Phase 1.5)
        "ceo_prenom":        enriched.get("ceo_prenom"),
        "ceo_nom":           enriched.get("ceo_nom"),
        "ceo_source":        enriched.get("ceo_source"),
        "email_valide":      enriched.get("email_valide"),
        "email_source":      enriched.get("email_source"),
        "copywriting_mode":  enriched.get("copywriting_mode"),
        "is_catch_all":      enriched.get("is_catch_all", False),
        "mx_host":           enriched.get("mx_host"),
        "telephone":         enriched.get("telephone"),
    }, ensure_ascii=False)
