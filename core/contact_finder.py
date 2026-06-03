# -*- coding: utf-8 -*-
"""
core/contact_finder.py — Module unifié de recherche de contacts

Point d'entrée unique pour tous les scrapers, agents et services.

Étant donné un URL et un nom d'entreprise optionnel, trouve :
  - Email de contact (visible sur le site)
  - Numéro de téléphone
  - Nom du CEO / gérant
  - Email validé SMTP (direct ou via permutations CEO)

Chaîne d'enrichissement (dégradation gracieuse) :
  1. Scraping site web (30+ pages, parallèle, Playwright fallback)
  2. Patterns anti-spam masqués (atob, [at], etc.)
  3. SMTP guess (contact@, info@, etc. via MX)
  4. CEO : API Gouv.fr → Groq → Ollama local
  5. Permutations prénom.nom → validation SMTP

Aucune API payante requise. Groq (optionnel) améliore la détection CEO.

Usage:
    from core.contact_finder import find_contacts, find_email

    result = find_contacts("https://dupont-solar.fr", "Dupont Solar")
    # → {email_valide, telephone, ceo_prenom, ceo_nom, ...}

    email = find_email("https://dupont-solar.fr")
    # → "contact@dupont-solar.fr" ou None
"""

import logging
import re
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ─── Regex téléphone FR ────────────────────────────────────────────────────────

_PHONE_RE = re.compile(
    r"(?:(?:\+|00)33[\s.\-]?(?:\(0\)[\s.\-]?)?|0)"
    r"[1-9](?:[\s.\-]?\d{2}){4}"
)


# ─── API publique ──────────────────────────────────────────────────────────────

def find_contacts(
    url: str,
    company_name: str = "",
    *,
    enrich_ceo: bool = True,
    fast_mode: bool = False,
) -> dict:
    """
    Trouve tous les contacts disponibles pour un site web.

    Args:
        url:          URL du site (http:// ou https://)
        company_name: Nom de l'entreprise (améliore la détection CEO)
        enrich_ceo:   Tenter d'identifier le CEO (défaut True)

    Returns:
        {
            "email_contact":    str | None,  # meilleur email trouvé sur le site
            "email_valide":     str | None,  # email validé SMTP
            "email_source":     str,          # origine de l'email
            "copywriting_mode": str,          # 'direct' | 'transfert'
            "is_catch_all":     bool,
            "mx_host":          str | None,
            "telephone":        str | None,
            "ceo_prenom":       str | None,
            "ceo_nom":          str | None,
            "ceo_prenom_norm":  str | None,
            "ceo_nom_norm":     str | None,
            "ceo_source":       str,
        }
    """
    if not url:
        return _empty()

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    parsed  = urlparse(url)
    domain  = parsed.netloc.lstrip("www.") or url
    result  = _empty()

    # ── Étape 1 : Email depuis le site web ────────────────────────────────────
    try:
        from scraper.email_finder import find_email_all_methods
        ef = find_email_all_methods(url, fast_mode=fast_mode)
        if ef.get("email"):
            result["email_contact"] = ef["email"]
            result["email_source"]  = ef.get("source", "site")
            logger.debug(f"[contact_finder] {domain} — email site: {ef['email']}")
    except Exception as e:
        logger.debug(f"[contact_finder] email_finder failed for {domain}: {e}")

    # ── Étape 2 : Téléphone ───────────────────────────────────────────────────
    try:
        result["telephone"] = _extract_phone_from_url(url)
    except Exception:
        pass

    # ── Étape 3 : CEO ─────────────────────────────────────────────────────────
    if enrich_ceo:
        try:
            from sniper.enrichment.ceo_finder import find_ceo
            name = company_name or _company_from_domain(domain)
            ceo  = find_ceo(name, domain, url)
            result.update({
                "ceo_prenom":      ceo.get("ceo_prenom"),
                "ceo_nom":         ceo.get("ceo_nom"),
                "ceo_prenom_norm": ceo.get("ceo_prenom_norm"),
                "ceo_nom_norm":    ceo.get("ceo_nom_norm"),
                "ceo_source":      ceo.get("ceo_source", "not_found"),
            })
            logger.debug(
                f"[contact_finder] {domain} — CEO: "
                f"{ceo.get('ceo_prenom')} {ceo.get('ceo_nom')} "
                f"({ceo.get('ceo_source')})"
            )
        except Exception as e:
            logger.debug(f"[contact_finder] ceo_finder failed for {domain}: {e}")

    # ── Étape 4 : Validation SMTP + permutations CEO ──────────────────────────
    try:
        from sniper.enrichment.email_permutations import generate_for_lead
        from sniper.enrichment.smtp_validator import validate as smtp_validate

        # generate_for_lead attend: ceo_prenom_norm, ceo_nom_norm, domaine/site_web
        lead_dict = {**result, "domaine": url, "site_web": url}
        permutations = generate_for_lead(lead_dict)

        email_fallback = result.get("email_contact")
        if email_fallback and "," in email_fallback:
            email_fallback = email_fallback.split(",")[0].strip()

        smtp = smtp_validate(
            permutations=permutations,
            domain=domain,
            email_contact_fallback=email_fallback,
        )
        result.update({
            "email_valide":     smtp.get("email_valide"),
            "email_source":     smtp.get("email_source", result["email_source"]),
            "copywriting_mode": smtp.get("copywriting_mode", "transfert"),
            "is_catch_all":     smtp.get("is_catch_all", False),
            "mx_host":          smtp.get("mx_host"),
        })
        logger.debug(
            f"[contact_finder] {domain} — smtp: "
            f"{smtp.get('email_valide')} mode={smtp.get('copywriting_mode')}"
        )
    except Exception as e:
        logger.debug(f"[contact_finder] smtp_validator failed for {domain}: {e}")

    logger.info(
        f"[contact_finder] {domain} → "
        f"email={result.get('email_valide') or result.get('email_contact') or '—'} "
        f"tel={result.get('telephone') or '—'} "
        f"CEO={result.get('ceo_prenom') or ''} {result.get('ceo_nom') or ''} "
        f"mode={result.get('copywriting_mode', '—')}"
    )
    return result


def find_email(url: str) -> Optional[str]:
    """
    Raccourci : retourne uniquement l'email validé (ou email_contact en fallback).

    Args:
        url: URL du site web

    Returns:
        Email ou None
    """
    result = find_contacts(url, enrich_ceo=False)
    return result.get("email_valide") or result.get("email_contact")


def find_phone(url: str) -> Optional[str]:
    """
    Raccourci : retourne uniquement le téléphone.

    Args:
        url: URL du site web

    Returns:
        Téléphone formaté ou None
    """
    if not url:
        return None
    try:
        return _extract_phone_from_url(url)
    except Exception:
        return None


# ─── Utilitaires internes ──────────────────────────────────────────────────────

def _empty() -> dict:
    return {
        "email_contact":    None,
        "email_valide":     None,
        "email_source":     "not_found",
        "copywriting_mode": "transfert",
        "is_catch_all":     False,
        "mx_host":          None,
        "telephone":        None,
        "ceo_prenom":       None,
        "ceo_nom":          None,
        "ceo_prenom_norm":  None,
        "ceo_nom_norm":     None,
        "ceo_source":       "not_found",
    }


def _company_from_domain(domain: str) -> str:
    """Déduit un nom d'entreprise approximatif depuis le domaine."""
    name = domain.split(".")[0].replace("-", " ").replace("_", " ")
    return name.title()


def _extract_phone_from_url(url: str) -> Optional[str]:
    """Tente d'extraire un téléphone FR depuis la homepage et la page /contact."""
    import requests

    headers = {"User-Agent": "Mozilla/5.0"}
    paths   = ["", "/contact", "/nous-contacter", "/coordonnees"]

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    parsed   = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    for path in paths:
        try:
            resp = requests.get(
                base_url + path, headers=headers, timeout=6, allow_redirects=True
            )
            if resp.status_code != 200:
                continue
            phone = _parse_phone(resp.text)
            if phone:
                return phone
        except Exception:
            continue

    return None


def _parse_phone(html: str) -> Optional[str]:
    """Extrait et normalise un numéro de téléphone FR depuis du HTML."""
    matches = _PHONE_RE.findall(html)
    if not matches:
        return None
    phone = re.sub(r"[\s.\-]", "", matches[0])
    if phone.startswith("+33"):
        phone = "0" + phone[3:]
    elif phone.startswith("0033"):
        phone = "0" + phone[4:]
    return phone
