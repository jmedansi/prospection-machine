# -*- coding: utf-8 -*-
"""
sniper/copywriter.py — Génération d'emails Sniper par tag_urgence

Lire sniper/README.md avant toute modification.

Responsabilité unique :
  - Charger le template HTML adapté au tag_urgence
  - Injecter les données du lead (nom, site, score, CMS...)
  - Retourner (email_objet, email_corps_html)

NE PAS importer depuis copywriter/ ou auditeur/ (modules Maps).
NE PAS faire d'appel LLM.
NE PAS approuver automatiquement.
"""

import os
import re
import logging
from typing import Optional

from core.template_renderer import render_template, extract_subject

logger = logging.getLogger(__name__)

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

# Routing par source (prioritaire) puis par tag pour ADS
_SOURCE_TEMPLATE_MAP = {
    "ads":    None,               # → fallback sur tag ci-dessous
    "fb_ads": None,               # → fallback sur tag ci-dessous (creation ou perf/secu)
    "ecom":   "email_ecom.html",
    "tech":   "email_ecom.html",  # legacy alias
    "jobs":   "email_jobs.html",
    "bodacc": "email_bodacc.html",
}

# Pour source=ads : routing par tag_urgence
_ADS_TAG_MAP = {
    "perf":          "email_perf.html",
    "securite":      "email_securite.html",
    "perf+securite": "email_perf.html",
    "creation":      "email_creation.html",
}

_FALLBACK_TEMPLATE = "email_ads.html"


def _resolve_template(source: str, tag: str) -> str:
    source = (source or "").lower()
    tag    = (tag or "perf").lower()
    tpl = _SOURCE_TEMPLATE_MAP.get(source)
    if tpl:
        return tpl
    # source=ads ou inconnu → tag
    return _ADS_TAG_MAP.get(tag, _FALLBACK_TEMPLATE)


def generate_email(
    nom:          str,
    site:         str,
    tag:          str,
    score:        Optional[int] = None,
    lcp_ms:       Optional[int] = None,
    cms:          Optional[str] = None,
    server:       Optional[str] = None,
    niveau:       int           = 0,
    lien_rapport: str           = "https://incidenx.com",
    source:       str           = "ads",
    entreprise:   Optional[str] = None,
) -> tuple[str, str]:
    """
    Génère l'email Sniper pour un lead qualifié.

    Args:
        nom:          Nom de l'entreprise
        site:         URL du site (ex: https://example.com)
        tag:          tag_urgence — 'perf' | 'securite' | 'perf+securite'
        score:        Score PageSpeed mobile (0-100)
        lcp_ms:       LCP en millisecondes
        cms:          CMS détecté (ex: 'WordPress', 'PrestaShop')
        niveau:       Niveau d'urgence (1-5) — non utilisé dans le template mais utile pour logs
        lien_rapport: URL du rapport (défaut: incidenx.com)

    Returns:
        (email_objet, email_corps_html)
    """
    # Valeurs affichées
    lcp_s    = f"{lcp_ms / 1000:.1f}" if lcp_ms else "?"
    score_s  = str(int(score)) if score is not None else "?"
    cms_s    = cms or "votre CMS"
    server_s = server or "votre serveur"
    nom_s    = nom or "votre site"

    # Nettoyage du nom (retirer URLs, parenthèses parasites)
    nom_s = re.sub(r"https?://\S+", "", nom_s).strip()
    nom_s = re.sub(r"\s{2,}", " ", nom_s).strip()

    entreprise_s = entreprise or nom_s
    site_display = re.sub(r"^https?://", "", site or "").rstrip("/")

    template_path = os.path.join(TEMPLATES_DIR, _resolve_template(source, tag))
    html = render_template(template_path, {
        "{{NOM}}":          nom_s,
        "{{ENTREPRISE}}":   entreprise_s,
        "{{SITE}}":         site_display,
        "{{SCORE}}":        score_s,
        "{{LCP}}":          lcp_s,
        "{{CMS}}":          cms_s,
        "{{SERVER}}":       server_s,
        "{{LIEN_RAPPORT}}": lien_rapport,
    })

    email_objet = extract_subject(html)

    # Injecter les valeurs dans l'objet aussi
    email_objet = (
        email_objet
        .replace("{{NOM}}",   nom_s)
        .replace("{{CMS}}",   cms_s)
        .replace("{{SCORE}}", score_s)
        .replace("{{LCP}}",   lcp_s)
    )

    logger.info(f"Email Sniper généré — {nom_s} | source={source} | tag={tag} | niveau={niveau}")
    return email_objet, html
