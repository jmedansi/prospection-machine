# -*- coding: utf-8 -*-
"""
scraper/sniper/keyword_bank.py — Banque de mots-clés pour le pipeline Sniper Ads

Objectif : 100 leads qualifiés/jour
Math : 10 keywords × 5 pages × ~3 annonceurs/page = ~150 bruts → ~100 qualifiés après scoring

Rotation journalière : on tire un lot différent chaque jour pour ne pas repasser
sur les mêmes annonceurs (budget Google se réinitialise à minuit mais pool tourne).
"""

import random
from datetime import date
from typing import List

# ─── Banque complète ──────────────────────────────────────────────────────────
# Secteurs à fort budget pub Google = sites souvent mal optimisés

_BANK = {
    "artisanat": [
        "serrurier urgence",
        "plombier urgence",
        "électricien urgence",
        "chauffagiste urgence",
        "dépannage plomberie",
        "installation chaudière",
        "débouchage canalisation",
        "réparation fuite eau",
        "serrurier pas cher",
        "ouverture de porte",
        "vitrerie urgence",
        "climatisation installation",
        "pompe à chaleur installation",
        "ramonage cheminée",
        "toiture réparation",
        "couvreur urgence",
        "peintre en bâtiment",
        "carreleur professionnel",
        "menuisier aluminium",
        "store banne installation",
    ],
    "services_pro": [
        "expert comptable PME",
        "avocat droit des affaires",
        "cabinet recrutement",
        "agence de communication",
        "agence SEO",
        "agence publicité en ligne",
        "formation professionnelle CPF",
        "bilan de compétences",
        "coaching professionnel",
        "conseil en stratégie entreprise",
        "externalisation comptabilité",
        "secrétariat externalisé",
        "traduction professionnelle",
        "photographe corporate",
        "vidéaste entreprise",
    ],
    # santé/bien-être retiré car la plupart ne font pas de publicité en France
    "immobilier": [
        "agence immobilière vente",
        "promoteur immobilier",
        "gestion locative",
        "chasseur immobilier",
        "diagnostiqueur immobilier",
        "déménagement entreprise",
        "garde meuble stockage",
        "location utilitaire",
        "home staging professionnel",
        "architecte d'intérieur",
        "décorateur intérieur",
        "cuisiniste sur mesure",
        "dressing sur mesure",
        "parquet installation",
        "isolation thermique",
    ],
    "auto_moto": [
        "garage automobile",
        "carrosserie réparation",
        "révision voiture",
        "contrôle technique auto",
        "vente voiture occasion",
        "leasing voiture",
        "assurance auto pas cher",
        "auto école permis",
        "transport personnes VTC",
        "location voiture longue durée",
    ],
    "formation_education": [
        "formation comptabilité",
        "formation marketing digital",
        "formation gestion de projet",
        "école de commerce",
        "cours particuliers",
        "soutien scolaire",
        "formation développement web",
        "formation Excel",
        "permis accéléré",
        "formation HACCP restauration",
    ],
    "ecommerce_retail": [
        "boutique vêtements en ligne",
        "bijouterie en ligne",
        "mobilier design",
        "matelas en ligne",
        "cosmétiques naturels",
        "compléments alimentaires sport",
        "équipement professionnel restauration",
        "fournitures bureau",
        "cadeaux personnalisés entreprise",
        "impression en ligne",
    ],
    "tech_logiciel": [
        "logiciel gestion PME",
        "ERP PME",
        "logiciel caisse enregistreuse",
        "CRM commercial",
        "logiciel RH paie",
        "hébergement web",
        "cybersécurité entreprise",
        "infogérance informatique",
        "développement application mobile",
        "création site e-commerce",
    ],
    "evenementiel": [
        "organisation événement entreprise",
        "location salle séminaire",
        "traiteur événement",
        "location matériel événementiel",
        "photographe mariage",
        "vidéaste mariage",
        "DJ mariage",
        "fleuriste mariage",
        "wedding planner",
        "location limousine",
    ],
    "finance_assurance": [
        "courtier assurance",
        "assurance professionnelle",
        "mutuelle entreprise",
        "rachat de crédit",
        "crédit immobilier",
        "investissement immobilier",
        "gestion patrimoine",
        "conseiller financier",
        "assurance habitation",
        "prévoyance retraite",
    ],
}

# Toutes les keywords à plat
ALL_KEYWORDS: List[str] = [kw for kws in _BANK.values() for kw in kws]

# ─── Banque e-commerce (boutiques en ligne) ───────────────────────────────────
# Mots-clés produits → Google remonte naturellement les boutiques WooCommerce/
# PrestaShop/Shopify dans les annonces et les résultats organiques.

_ECOM_BANK: List[str] = [
    # Mode / vêtements / accessoires
    "boutique vetements femme en ligne",
    "acheter chaussures femme pas cher",
    "bijoux fantaisie boutique en ligne",
    "maroquinerie sac cuir boutique en ligne",
    "lingerie boutique en ligne",
    "vetements enfants boutique en ligne",
    "mode homme boutique en ligne",
    "accessoires mode boutique en ligne",
    # Beauté / cosmétiques
    "cosmetiques naturels boutique en ligne",
    "parfum pas cher boutique en ligne",
    "maquillage bio boutique en ligne",
    "soins visage boutique en ligne",
    # Maison / décoration
    "decoration interieur boutique en ligne",
    "luminaire design boutique en ligne",
    "linge de maison boutique en ligne",
    "vaisselle design boutique en ligne",
    # Sport / outdoor
    "equipement sport boutique en ligne",
    "velo electrique boutique en ligne",
    "materiel musculation boutique en ligne",
    "randonnee equipement boutique en ligne",
    # High-tech / gaming
    "accessoires smartphone boutique en ligne",
    "gaming accessoires boutique en ligne",
    "PC portable boutique en ligne",
    "son casque audio boutique en ligne",
    # Santé / bien-être
    "complements alimentaires boutique en ligne",
    "huiles essentielles boutique en ligne",
    "materiel medical boutique en ligne",
    # Enfant / bébé / jouets
    "jouets enfants boutique en ligne",
    "vetements bebe boutique en ligne",
    "jeux de societe boutique en ligne",
    # Alimentation / épicerie
    "epicerie fine produits boutique en ligne",
    "the cafe boutique en ligne",
    "vin cave boutique en ligne",
    "chocolat artisanal boutique en ligne",
    # Animaux
    "accessoires chien chat boutique en ligne",
    "alimentation animaux boutique en ligne",
    # Jardinage / bricolage
    "jardinerie boutique en ligne",
    "outillage bricolage boutique en ligne",
    # Arts / loisirs créatifs
    "fournitures loisirs creatifs boutique en ligne",
    "instruments musique boutique en ligne",
]


def get_daily_batch(n: int = 10, seed: int | None = None) -> List[str]:
    """
    Retourne un lot de n mots-clés pour aujourd'hui.
    Le seed basé sur la date garantit un lot différent chaque jour
    mais reproductible si on relance dans la journée.
    """
    if seed is None:
        today = date.today()
        seed = today.year * 10000 + today.month * 100 + today.day

    rng = random.Random(seed)
    shuffled = list(ALL_KEYWORDS)
    rng.shuffle(shuffled)
    return shuffled[:n]


def get_ecom_daily_batch(n: int = 8, seed: int | None = None) -> List[str]:
    """
    Retourne un lot de n mots-clés e-com pour aujourd'hui.
    Rotation quotidienne reproductible (seed = date).
    Avec 42 mots-clés et n=8, le cycle complet dure ~5 jours.
    """
    if seed is None:
        today = date.today()
        seed = today.year * 10000 + today.month * 100 + today.day + 1  # +1 pour diverger du lot Ads

    rng = random.Random(seed)
    shuffled = list(_ECOM_BANK)
    rng.shuffle(shuffled)
    return shuffled[:n]


def get_batch_by_sector(sector: str, n: int = 10) -> List[str]:
    """Retourne des keywords d'un secteur spécifique."""
    kws = _BANK.get(sector, [])
    return kws[:n]


def get_all_sectors() -> List[str]:
    return list(_BANK.keys())
