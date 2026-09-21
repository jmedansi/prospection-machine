# -*- coding: utf-8 -*-
"""
scraper/zone_agent.py — Agent de découverte géographique

Utilise Groq (LLaMA 3.3 70B) pour identifier automatiquement
toutes les sous-zones (arrondissements, quartiers, communes)
d'une ville afin de contourner la limite de ~120 résultats
de Google Maps par requête.
"""
import json
import logging
import sys
import os

# Ajout du parent pour importer config_manager
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

logger = logging.getLogger(__name__)


def get_city_subdivisions(city: str, max_zones: int = 30) -> list[str]:
    """
    Interroge Groq pour obtenir la liste des sous-zones d'une ville,
    telles qu'elles apparaissent dans les recherches Google Maps.

    Args:
        city:      Nom de la ville (ex: "Paris", "Lyon", "Cotonou")
        max_zones: Nombre maximum de zones à retourner (défaut: 30)

    Returns:
        Liste de chaînes de sous-zones (ex: ["Paris 1er", "Paris 2e", ...])
        Retourne une liste de variantes génériques en cas d'échec.
    """
    try:
        from config_manager import handle_llm_call

        prompt = f"""Tu es un expert en géographie urbaine.

Liste TOUTES les subdivisions de la ville "{city}" (arrondissements, quartiers, communes voisines) telles qu'elles apparaissent dans une recherche Google Maps.

Règles STRICTES :
- Utilise des noms exacts comme sur Google Maps (ex: "Paris 1er", "Lyon 6e", "Abidjan Cocody")
- Inclure les quartiers connus, les communes limitrophes importantes
- Maximum {max_zones} zones, triées du centre vers la périphérie
- Retourner UNIQUEMENT un tableau JSON valide, sans explication
- Format : ["zone1", "zone2", ...]

Ville : {city}"""

        print(f"   [ZoneAgent] Interrogation Groq pour les sous-zones de '{city}'...")
        raw = handle_llm_call(
            prompt=prompt,
            system="Tu es un assistant géographique. Réponds UNIQUEMENT avec du JSON valide, sans markdown ni explication.",
            model="llama-3.3-70b-versatile"
        )

        # Nettoyage de la réponse (parfois Groq wrappe dans ```json ... ```)
        cleaned = raw.strip()
        if "```" in cleaned:
            # Extraire le contenu entre les backticks
            import re
            match = re.search(r'```(?:json)?\s*([\s\S]*?)```', cleaned)
            if match:
                cleaned = match.group(1).strip()

        zones = json.loads(cleaned)

        if not isinstance(zones, list) or not zones:
            raise ValueError(f"Réponse invalide de Groq : {raw[:200]}")

        # Filtrage et déduplication
        zones = [str(z).strip() for z in zones if z and str(z).strip()]
        seen = set()
        unique_zones = []
        for z in zones:
            if z.lower() not in seen:
                seen.add(z.lower())
                unique_zones.append(z)

        print(f"   [ZoneAgent] {len(unique_zones)} sous-zones trouvées pour '{city}'")
        return unique_zones[:max_zones]

    except ImportError:
        logger.warning("config_manager non disponible — ZoneAgent désactivé")
        return _fallback_zones(city)
    except Exception as e:
        logger.error(f"[ZoneAgent] Erreur Groq pour '{city}': {e}")
        print(f"   [ZoneAgent] ⚠️ Erreur : {e} — Utilisation des zones génériques.")
        return _fallback_zones(city)


def _fallback_zones(city: str) -> list[str]:
    """
    Retourne des variantes génériques quand Groq est inaccessible.
    Couvre les orientations cardinales et les secteurs communs.
    """
    return [
        f"{city} centre",
        f"{city} centre-ville",
        f"{city} nord",
        f"{city} sud",
        f"{city} est",
        f"{city} ouest",
        f"{city} nord-est",
        f"{city} nord-ouest",
        f"{city} sud-est",
        f"{city} sud-ouest",
    ]


if __name__ == "__main__":
    # Test rapide
    city = sys.argv[1] if len(sys.argv) > 1 else "Lyon"
    zones = get_city_subdivisions(city)
    print(f"\n✅ Sous-zones pour '{city}' ({len(zones)}):")
    for i, z in enumerate(zones, 1):
        print(f"  {i:2}. {z}")
