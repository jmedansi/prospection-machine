# -*- coding: utf-8 -*-
"""
core/audit_data.py — Normalisation du JSON donnees_audit

Point d'entrée unique pour lire donnees_audit depuis la base.
Résout tous les aliases de clés (score_mobile/mobile_score, cms/ecommerce, etc.)
et retourne toujours un dict avec les clés canoniques.

Usage:
    from core.audit_data import parse_donnees_audit

    donnees = parse_donnees_audit(lead["donnees_audit"])
    score   = donnees["score_mobile"]   # toujours présent, jamais KeyError
"""

import json
import logging
from typing import Union

logger = logging.getLogger(__name__)

# Clés canoniques → aliases acceptés en lecture
# Format : {cle_canonique: [alias_1, alias_2, ...]}
_ALIASES = {
    "score_mobile":  ["mobile_score", "performance_score"],
    "score_desktop": ["desktop_score"],
    "cms":           ["ecommerce", "cms_detected", "framework"],
    "has_cdn":       ["cdn"],
    "has_waf":       ["waf"],
    "tag_urgence":   ["tag"],
}


def parse_donnees_audit(raw: Union[str, dict, None]) -> dict:
    """
    Parse et normalise donnees_audit.

    Args:
        raw: JSON string, dict déjà parsé, ou None.

    Returns:
        Dict avec clés canoniques, valeurs typées, jamais de KeyError.
        Les clés inconnues sont conservées telles quelles.
    """
    if raw is None:
        return _defaults()

    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            logger.warning("[audit_data] donnees_audit invalide (JSON malformé)")
            return _defaults()
    else:
        data = dict(raw)

    # Résolution des aliases → clé canonique
    for canonical, aliases in _ALIASES.items():
        if canonical not in data or data[canonical] is None:
            for alias in aliases:
                if data.get(alias) is not None:
                    data[canonical] = data[alias]
                    break

    # Valeurs par défaut pour les clés toujours attendues
    defaults = _defaults()
    for key, default_val in defaults.items():
        if key not in data or data[key] is None:
            data[key] = default_val

    # Typage strict des métriques numériques
    for int_key in ("score_mobile", "score_desktop", "score_seo",
                    "render_blocking_scripts", "page_size_kb", "heat_score"):
        try:
            data[int_key] = int(data[int_key] or 0)
        except (TypeError, ValueError):
            data[int_key] = 0

    for float_key in ("lcp_ms", "fcp_ms"):
        try:
            data[float_key] = float(data[float_key] or 0)
        except (TypeError, ValueError):
            data[float_key] = 0.0

    for bool_key in ("has_cdn", "has_waf", "has_https", "is_catch_all",
                     "has_gtm", "has_ga"):
        data[bool_key] = bool(data.get(bool_key))

    return data


def _defaults() -> dict:
    return {
        # Performance
        "score_mobile":            0,
        "score_desktop":           0,
        "score_seo":               0,
        "lcp_ms":                  0.0,
        "fcp_ms":                  0.0,
        "render_blocking_scripts": 0,
        "page_size_kb":            0,
        # Infrastructure
        "cms":       None,
        "server":    None,
        "has_cdn":   False,
        "has_waf":   False,
        "has_https": True,
        "has_gtm":   False,
        "has_ga":    False,
        # Qualification
        "tag_urgence":  None,
        "heat_score":   0,
        "reason":       "",
        # CEO
        "ceo_prenom":  None,
        "ceo_nom":     None,
        "ceo_source":  "not_found",
        # Email
        "email_valide":      None,
        "email_source":      "not_found",
        "copywriting_mode":  "transfert",
        "is_catch_all":      False,
        "mx_host":           None,
        "telephone":         None,
        # BODACC
        "siren": None,
        "naf":   None,
    }
