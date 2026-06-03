# -*- coding: utf-8 -*-
"""
core/email_constants.py — Constantes partagées pour la recherche d'emails

Source unique pour :
  - EMAIL_EXCLUDE_PATTERNS  : emails/domaines à ne jamais retenir
  - EMAIL_PRIORITY          : score par préfixe (plus bas = meilleur)
  - SMTP_VARIANTS           : préfixes à tester par SMTP guess
  - EMAIL_REGEX             : regex de base pour extraction

Remplace les deux listes divergentes dans scraper/email_finder.py
et sniper/enrichment/contact_finder.py.
"""

import re

# ── Patterns à exclure systématiquement ────────────────────────────────────────
# (noreply, plateformes tierces, domaines jetables, artefacts JS)
EMAIL_EXCLUDE_PATTERNS = [
    # Fonctionnels génériques
    "noreply@", "no-reply@", "donotreply@", "webmaster@", "abuse@",
    "wordpress@", "admin@", "root@", "postmaster@",
    # Plateformes
    "@sentry.io", "@googleapis.com", "@google-analytics.com",
    "@facebook.com", "@twitter.com", "@instagram.com", "@linkedin.com",
    "@wix.com", "@squarespace.com", "@wixsite.com", "@weebly.com", "@shopify.com",
    # Fictifs / exemples
    "mysite.com", "votresite.com", "monsite.com", "yoursite.com",
    "example.com", "domain.com", "test.com", "localhost",
    # Artefacts de numéros de version dans le HTML
    "@5.1.3", "@4.0", "@1.16.1", "@3.", "@2.", "@1.",
    # Artefacts librairies JS
    "bootstrap", "popper.js", "jquery", "fontawesome", "googleads",
    # Domaines temporaires / jetables
    "yopmail.com", "10minutemail.com", "temp-mail.org", "guerrillamail.com",
    "mailinator.com", "tempmail.com", "fakeinbox.com", "throwaway.email",
    "dispostable.com", "sharklasers.com", "spam4.me", "grr.la",
]

# ── Priorité par préfixe (plus bas = meilleur) ─────────────────────────────────
# Format dict : compatible avec scraper/email_finder.py (contact@ avec @)
EMAIL_PRIORITY = {
    "contact@":    1,
    "info@":       2,
    "bonjour@":    3,
    "hello@":      4,
    "accueil@":    5,
    "direction@":  6,
    "secretariat@": 7,
    "commercial@": 8,
    "vente@":      9,
    "sales@":      10,
    "support@":    11,
}

# Liste ordonnée des préfixes (sans @) pour les modules qui scorent par index
EMAIL_PRIORITY_PREFIXES = [p.rstrip("@") for p in EMAIL_PRIORITY]

# ── Variants SMTP à tester (guess par MX) ─────────────────────────────────────
SMTP_VARIANTS = [
    "contact@{domain}",
    "info@{domain}",
    "bonjour@{domain}",
    "hello@{domain}",
    "accueil@{domain}",
    "direction@{domain}",
]

# ── Regex de base ──────────────────────────────────────────────────────────────
EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)


def score_email(email: str) -> int:
    """
    Retourne le score de priorité d'un email (plus bas = meilleur).
    Un email non reconnu reçoit un score > tous les préfixes connus.
    """
    email_lower = email.lower()
    for pattern, priority in EMAIL_PRIORITY.items():
        if email_lower.startswith(pattern):
            return priority
    return len(EMAIL_PRIORITY) + 1


def is_excluded(email: str) -> bool:
    """Retourne True si l'email doit être ignoré."""
    email_lower = email.lower()
    return any(excl in email_lower for excl in EMAIL_EXCLUDE_PATTERNS)
