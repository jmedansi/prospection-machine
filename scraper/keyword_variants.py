# -*- coding: utf-8 -*-
"""
scraper/keyword_variants.py
Génère des variantes de mots-clés via LLM pour élargir la recherche Google Maps.
"""
import json
import logging
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

logger = logging.getLogger(__name__)


def generate_keyword_variants(keyword: str, city: str, country: str = 'fr',
                               max_variants: int = 8) -> list[str]:
    """
    Génère des variantes de mots-clés pour élargir la recherche Google Maps.

    Ex: "hôtel Cotonou" → ["hôtel boutique Cotonou", "bnb Cotonou",
        "auberge Cotonou", "guest house Cotonou", ...]

    Args:
        keyword:      Mot-clé de base (ex: "hôtel")
        city:         Ville ciblée (ex: "Cotonou")
        country:      Code pays (fr, bj, be, ...)
        max_variants: Nombre max de variantes à retourner

    Returns:
        Liste de variantes de mots-clés (ex: ["hôtel boutique", "bnb", ...])
        Retourne [keyword] en cas d'erreur.
    """
    try:
        from config_manager import handle_llm_call

        country_name = {
            "fr": "française", "bj": "béninoise", "be": "belge",
            "ch": "suisse", "lu": "luxembourgeoise",
        }.get(country, "française")

        prompt = f"""Tu es un expert en recherche Google Maps pour la prospection B2B.

Génère {max_variants} variantes du mot-clé "{keyword}" pour la ville "{city}" (contexte {country_name}).

Règles :
- Inclure des synonymes et termes proches
- Adapter au contexte local ({country_name})
- Inclure des termes anglais si couramment utilisés (ex: "guest house", "boutique hotel")
- Retourner UNIQUEMENT un tableau JSON valide, sans markdown ni explication
- Format : ["variante1", "variante2", ...]
- NE PAS inclure la ville dans les variantes (sera ajoutée automatiquement)

Exemples pour "hôtel" :
["hôtel", "hôtel boutique", "bnb", "auberge", "guest house", "maison d'hôtes", "résidence", "lodging"]

Mot-clé : {keyword}
Ville : {city}"""

        print(f"   [KeywordVariants] Génération de variantes pour '{keyword}' à {city}...")
        raw = handle_llm_call(
            prompt=prompt,
            system="Tu es un assistant de prospection. Réponds UNIQUEMENT avec du JSON valide, sans markdown ni explication.",
            model="llama-3.3-70b-versatile"
        )

        # Nettoyage de la réponse
        cleaned = raw.strip()
        if "```" in cleaned:
            import re
            match = re.search(r'```(?:json)?\s*([\s\S]*?)```', cleaned)
            if match:
                cleaned = match.group(1).strip()

        variants = json.loads(cleaned)

        if not isinstance(variants, list) or not variants:
            raise ValueError(f"Réponse invalide : {raw[:200]}")

        # Filtrer et dédupliquer
        seen = set()
        result = []
        for v in variants:
            v_str = str(v).strip()
            if v_str and v_str.lower() not in seen and v_str.lower() != keyword.lower():
                seen.add(v_str.lower())
                result.append(v_str)

        # Toujours inclure le mot-clé original en premier
        final = [keyword] + result[:max_variants]
        print(f"   [KeywordVariants] {len(final)} variantes générées")
        return final

    except ImportError:
        logger.warning("config_manager non disponible — variantes LLM désactivées")
        return [keyword]
    except Exception as e:
        logger.error(f"[KeywordVariants] Erreur : {e}")
        print(f"   [KeywordVariants] ⚠️ Erreur : {e} — Utilisation du mot-clé original")
        return [keyword]


if __name__ == "__main__":
    keyword = sys.argv[1] if len(sys.argv) > 1 else "hôtel"
    city = sys.argv[2] if len(sys.argv) > 2 else "Cotonou"
    country = sys.argv[3] if len(sys.argv) > 3 else "bj"
    variants = generate_keyword_variants(keyword, city, country)
    print(f"\nVariantes pour '{keyword}' à {city} :")
    for i, v in enumerate(variants, 1):
        print(f"  {i}. {v}")
