# -*- coding: utf-8 -*-
"""
sniper/enrichment/email_permutations.py — Générateur de permutations email

Lire sniper/enrichment/README.md avant toute modification.

Entrée  : prenom_norm, nom_norm, domain  (tous normalisés — sans accents)
Sortie  : liste ordonnée par probabilité décroissante

Probabilités B2B françaises (ordre empirique) :
  1. prenom.nom@     ~35%
  2. p.nom@          ~20%
  3. prenom@         ~15%  (fréquent dans les petites structures)
  4. pnom@           ~15%
  5. nom@            ~10%
  6. prenomnom@       ~5%
"""

from typing import Optional


def generate(
    prenom_norm: str,
    nom_norm:    str,
    domain:      str,
) -> list[str]:
    """
    Génère les permutations email probables pour un décideur.

    Args:
        prenom_norm: Prénom normalisé (ex: "jean")
        nom_norm:    Nom normalisé    (ex: "dupont")
        domain:      Domaine          (ex: "dupont-solar.fr")

    Returns:
        Liste de candidats ordonnés par probabilité décroissante
    """
    p = prenom_norm.lower().strip()
    n = nom_norm.lower().strip()
    d = domain.lower().strip().lstrip("www.")

    if not p or not n or not d:
        return []

    # Initiale du prénom
    pi = p[0]

    candidates = [
        f"{p}.{n}@{d}",      # jean.dupont@    ~35%
        f"{pi}.{n}@{d}",     # j.dupont@       ~20%
        f"{p}@{d}",          # jean@           ~15%
        f"{pi}{n}@{d}",      # jdupont@        ~15%
        f"{n}@{d}",          # dupont@         ~10%
        f"{p}{n}@{d}",       # jeandupont@      ~5%
    ]

    # Dédupliquer en conservant l'ordre
    seen, unique = set(), []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)

    return unique


def generate_for_lead(lead: dict) -> list[str]:
    """
    Wrapper : génère les permutations depuis un dict lead enrichi.

    Utilise les clés : ceo_prenom_norm, ceo_nom_norm, domaine/site_web
    Retourne [] si les données sont incomplètes.
    """
    prenom = lead.get("ceo_prenom_norm") or ""
    nom    = lead.get("ceo_nom_norm") or ""

    url    = lead.get("domaine") or lead.get("site_web") or ""
    import re
    domain = re.sub(r"^https?://", "", url).rstrip("/").split("/")[0].lstrip("www.")

    return generate(prenom, nom, domain)
