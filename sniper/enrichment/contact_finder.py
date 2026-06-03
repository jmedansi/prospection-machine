# -*- coding: utf-8 -*-
"""
sniper/enrichment/contact_finder.py — Email générique + téléphone depuis le site

Lire sniper/enrichment/README.md avant toute modification.

Cherche dans cet ordre :
  1. Email visible dans le HTML (mailto:, texte)
  2. Page /contact, /nous-contacter, /about
  3. Téléphone (regex sur le HTML)

N'utilise PAS Hunter.io ni email_finder.py (Maps) pour rester isolé.
Adapté aux sites B2B : priorité contact@, info@, bonjour@...
"""

import re
import logging
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

from core.email_constants import EMAIL_REGEX as _EMAIL_REGEX, is_excluded, score_email as _score_email

_CONTACT_PATHS = [
    "/contact", "/nous-contacter", "/contactez-nous",
    "/about", "/a-propos", "/qui-sommes-nous",
    "/mentions-legales", "/legal",
]

_PHONE_REGEX = re.compile(
    r"(?:(?:\+|00)33[\s.\-]?(?:\(0\)[\s.\-]?)?|0)"
    r"[1-9](?:[\s.\-]?\d{2}){4}"
)


def _fetch(url: str, timeout: int = 8) -> Optional[str]:
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp    = requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code == 200:
            return resp.text
    except Exception:
        pass
    return None


def _extract_emails(html: str, domain: str) -> list[str]:
    """Extrait les emails appartenant au domaine depuis un HTML."""
    found = _EMAIL_REGEX.findall(html)
    domain_base = domain.lstrip("www.")
    filtered = [
        e.lower() for e in found
        if domain_base in e.lower() and not is_excluded(e)
    ]
    seen = set()
    unique = []
    for e in filtered:
        if e not in seen:
            seen.add(e)
            unique.append(e)
    unique.sort(key=_score_email)
    return unique


def _extract_phone(html: str) -> Optional[str]:
    matches = _PHONE_REGEX.findall(html)
    if matches:
        phone = re.sub(r"[\s.\-]", "", matches[0])
        # Normaliser au format 0X XX XX XX XX
        if phone.startswith("+33"):
            phone = "0" + phone[3:]
        elif phone.startswith("0033"):
            phone = "0" + phone[4:]
        return phone
    return None


def find_contact(url: str) -> dict:
    """
    Cherche email de contact et téléphone sur un site B2B.

    Args:
        url: URL du site (https://...)

    Returns:
        {
            "email_contact": str | None,
            "telephone":     str | None,
            "email_source":  str,   # 'homepage' | 'contact_page' | 'not_found'
        }
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    parsed     = urlparse(url)
    domain     = parsed.netloc.lstrip("www.")
    base_url   = f"{parsed.scheme}://{parsed.netloc}"

    result = {
        "email_contact": None,
        "telephone":     None,
        "email_source":  "not_found",
    }

    # ── 1. Page d'accueil ──────────────────────────────────────────────────────
    html = _fetch(url)
    if html:
        emails = _extract_emails(html, domain)
        if emails:
            result["email_contact"] = emails[0]
            result["email_source"]  = "homepage"

        phone = _extract_phone(html)
        if phone:
            result["telephone"] = phone

        # Chercher aussi dans les href mailto:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=re.compile(r"^mailto:", re.I)):
            raw = a["href"].replace("mailto:", "").split("?")[0].strip().lower()
            if "@" in raw and domain in raw:
                if not result["email_contact"] or _score_email(raw) < _score_email(result["email_contact"]):
                    result["email_contact"] = raw
                    result["email_source"]  = "homepage_mailto"

    # ── 2. Pages contact si email non trouvé ──────────────────────────────────
    if not result["email_contact"]:
        for path in _CONTACT_PATHS:
            page_url  = urljoin(base_url, path)
            page_html = _fetch(page_url)
            if not page_html:
                continue

            emails = _extract_emails(page_html, domain)
            if emails:
                result["email_contact"] = emails[0]
                result["email_source"]  = f"contact_page:{path}"
                break

            # Chercher mailto: sur la page contact
            soup = BeautifulSoup(page_html, "html.parser")
            for a in soup.find_all("a", href=re.compile(r"^mailto:", re.I)):
                raw = a["href"].replace("mailto:", "").split("?")[0].strip().lower()
                if "@" in raw:
                    result["email_contact"] = raw
                    result["email_source"]  = f"contact_page_mailto:{path}"
                    break
            if result["email_contact"]:
                break

            # Téléphone sur page contact si pas encore trouvé
            if not result["telephone"]:
                phone = _extract_phone(page_html)
                if phone:
                    result["telephone"] = phone

    logger.info(
        f"contact_finder: {domain} → "
        f"email={result['email_contact']} tel={result['telephone']} "
        f"source={result['email_source']}"
    )
    return result
