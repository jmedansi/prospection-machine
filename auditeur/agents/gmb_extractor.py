# -*- coding: utf-8 -*-
import json
import logging
from typing import Dict, Any
from config_manager import get_config

# Configuration du logger
logger = logging.getLogger(__name__)

def collect_gmb(keyword: str, city: str, gmb_initial: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    ÉTAPE 1 — Collecte/Normalisation GMB (Architecture Python Pur).
    Utilise les données fournies par le scraper si disponibles.
    """
    # Si on a déjà les données de base, on les normalise pour la suite des agents
    data = {
        "nom": keyword,
        "adresse": "Inconnue",
        "telephone": "S.O.",
        "site_web": None,
        "rating": 0,
        "nb_avis": 0,
        "photos_count": 10,
        "has_menu": False,
        "has_dishes_photos": True,
        "has_recent_post": True
    }

    if gmb_initial:
        # Helper pour convertir en nombre
        def to_num(val, default, type_factory=float):
            if val is None or str(val).strip() == "":
                return default
            try:
                # Gérer les virgules françaises
                if isinstance(val, str):
                    val = val.replace(",", ".").replace(" avis", "").replace(" reviews", "").strip()
                return type_factory(val)
            except (ValueError, TypeError):
                return default

        data.update({
            "adresse": gmb_initial.get("Adresse") or gmb_initial.get("adresse") or data["adresse"],
            "telephone": gmb_initial.get("Téléphone") or gmb_initial.get("telephone") or data["telephone"],
            "site_web": gmb_initial.get("Site web") or gmb_initial.get("site_web") or data["site_web"],
            "rating": to_num(gmb_initial.get("Note") or gmb_initial.get("rating"), data["rating"], float),
            "nb_avis": to_num(gmb_initial.get("Nombre d'avis") or gmb_initial.get("nb_avis"), data["nb_avis"], int)
        })
        
        print(f"   [Agent GMB] Données récupérées depuis le scraper pour {keyword}.")
    else:
        print(f"   [Agent GMB] Aucune donnée initiale pour {keyword}. Utilisation des valeurs par défaut.")

    return data
