# -*- coding: utf-8 -*-
"""
sniper/enrichment/smtp_validator.py — Façade vers core/deliverability

Lire sniper/enrichment/README.md avant toute modification.

La logique SMTP (MX, RCPT TO, catch-all, permutations) est centralisée dans
core/deliverability.py. Ce module expose l'interface Sniper inchangée.
"""

from core.deliverability import validate_with_permutations as _validate
from typing import Optional


def validate(
    permutations: list[str],
    domain: str,
    email_contact_fallback: Optional[str] = None,
) -> dict:
    """
    Valide les permutations email par SMTP.

    Returns:
        {email_valide, email_source, copywriting_mode, is_catch_all, mx_host}
    """
    return _validate(
        permutations=permutations,
        domain=domain,
        email_contact_fallback=email_contact_fallback,
    )
