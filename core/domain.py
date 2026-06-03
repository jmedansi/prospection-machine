# -*- coding: utf-8 -*-
"""
core/domain.py — Normalisation de domaine et d'URL

Source unique pour toute opération sur domaines/URLs dans les deux pipelines.
Remplace les 5 implémentations dispersées dans pre_filter.py, jobs_scraper.py,
scraper/main.py, imap_poller.py.

Usage:
    from core.domain import normalize_url, extract_domain, extract_domain_from_email
"""

import re
from typing import Optional
from urllib.parse import urlparse


def normalize_url(url: str) -> str:
    """
    Garantit que l'URL commence par https://.

    >>> normalize_url("dupont.fr")          → "https://dupont.fr"
    >>> normalize_url("http://dupont.fr")   → "http://dupont.fr"  (conservé)
    >>> normalize_url("https://dupont.fr")  → "https://dupont.fr"
    """
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        return "https://" + url
    return url


def extract_domain(url: str) -> str:
    """
    Extrait le domaine nu depuis une URL (sans www., sans chemin, sans port).

    >>> extract_domain("https://www.dupont-solar.fr/contact") → "dupont-solar.fr"
    >>> extract_domain("dupont-solar.fr")                     → "dupont-solar.fr"
    """
    url = normalize_url(url)
    parsed = urlparse(url)
    domain = parsed.netloc or url
    # Retirer port éventuel
    domain = domain.split(":")[0]
    # Retirer www.
    if domain.startswith("www."):
        domain = domain[4:]
    return domain.lower()


def extract_domain_from_email(email: str) -> str:
    """
    Extrait le domaine depuis une adresse email.

    >>> extract_domain_from_email("contact@dupont-solar.fr") → "dupont-solar.fr"
    """
    if "@" in (email or ""):
        return email.split("@", 1)[1].lower()
    return ""


def same_domain(url_or_email_a: str, url_or_email_b: str) -> bool:
    """
    Retourne True si les deux adresses appartiennent au même domaine racine.
    Fonctionne avec URLs et emails.
    """
    def _root(s: str) -> str:
        d = extract_domain_from_email(s) if "@" in s else extract_domain(s)
        parts = d.rsplit(".", 2)
        return ".".join(parts[-2:]) if len(parts) >= 2 else d

    return _root(url_or_email_a) == _root(url_or_email_b)
