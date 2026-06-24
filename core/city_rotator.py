# -*- coding: utf-8 -*-
"""
core/city_rotator.py — Rotation de villes pour atteindre le quota de leads

Usage dans n'importe quel pipeline :
    from core.city_rotator import CityRotator

    rotator = CityRotator(country="fr")
    extra_kws = rotator.next_batch("plombier urgence", batch_size=5)
    # → ["plombier urgence Paris", "plombier urgence Lyon", ...]

    # Après chaque passe :
    rotator.mark_used(extra_kws)  # ne repropose pas les mêmes villes
"""

import logging
import json
import os
from typing import List, Optional

logger = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(ROOT, "data", "used_cities.json")

# ─── Villes par pays, ordonnées par population (plus de prospects) ────────────

_CITIES: dict = {
    "fr": [
        # Top 20 métropoles
        "Paris", "Lyon", "Marseille", "Toulouse", "Nice",
        "Nantes", "Montpellier", "Strasbourg", "Bordeaux", "Lille",
        "Rennes", "Reims", "Saint-Étienne", "Toulon", "Le Havre",
        "Grenoble", "Dijon", "Angers", "Nîmes", "Villeurbanne",
        # Villes moyennes
        "Clermont-Ferrand", "Aix-en-Provence", "Brest", "Tours",
        "Amiens", "Limoges", "Annecy", "Perpignan", "Metz", "Besançon",
        "Orléans", "Rouen", "Mulhouse", "Caen", "Nancy", "Argenteuil",
        "Saint-Denis", "Roubaix", "Tourcoing", "Avignon",
        # Villes petites / bassins d'emploi
        "Bayonne", "Pau", "Lorient", "La Rochelle", "Poitiers",
        "Valence", "Dunkerque", "Aix-les-Bains", "Chambéry", "Colmar",
        "Troyes", "Chartres", "Bourges", "Auxerre", "Arras",
        "Calais", "Béziers", "Narbonne", "Montauban", "Angoulême",
        "Mérignac", "Pessac", "Boulogne-Billancourt", "Versailles",
        "Créteil", "Ivry-sur-Seine", "Vitry-sur-Seine", "Montreuil",
    ],
    "be": [
        "Bruxelles", "Anvers", "Gand", "Charleroi", "Liège",
        "Bruges", "Namur", "Louvain", "Mons", "Aalst",
        "La Louvière", "Courtrai", "Hasselt", "Ostende", "Tournai",
    ],
    "ch": [
        "Zurich", "Genève", "Bâle", "Lausanne", "Berne",
        "Winterthour", "Lucerne", "Saint-Gall", "Lugano", "Bienne",
        "Thoune", "Köniz", "La Chaux-de-Fonds", "Fribourg", "Schaffhouse",
    ],
    "lu": [
        "Luxembourg", "Esch-sur-Alzette", "Differdange", "Dudelange",
        "Pétange", "Sanem", "Hesperange", "Bertrange",
    ],
    "bj": [
        "Cotonou", "Porto-Novo", "Parakou", "Djougou", "Bohicon",
        "Abomey", "Natitingou", "Lokossa", "Comè", "Ouidah",
        "Sèmè-Kpodji", "Abomey-Calavi", "Allada", "Kétou", "Pobè",
        "Sakété", "Dassa-Zoumè", "Savalou", "Bassila", "Glo-Djigbé",
    ],
}


class CityRotator:
    """
    Gère la rotation des villes pour un scraper donné.

    Exemple complet :
        rotator = CityRotator(country="fr")

        # Passe 1 — mots-clés originaux (sans ville)
        leads_acceptes = 3
        min_leads = 20

        while leads_acceptes < min_leads and rotator.has_more():
            batch = rotator.next_batch("plombier paris", batch_size=5)
            # → ["plombier paris Marseille", "plombier paris Lyon", ...]
            # (Paris est dedupliqué automatiquement si déjà dans le keyword)
            new_leads = run_pipeline(batch)
            leads_acceptes += new_leads
            rotator.mark_used(batch)
    """

    def __init__(self, country: str = "fr", keywords: List[str] = None, source: str = "default"):
        country = country.lower()[:2]
        self._cities = list(_CITIES.get(country, _CITIES["fr"]))
        self._used: set = set()
        self._index: int = 0
        # On préfixe les mots-clés par la source pour isoler la mémorisation par scraper
        self._keywords = [f"{source}:{k.lower()}" for k in (keywords or [])]
        self._load_state()

    def _load_state(self):
        if not self._keywords or not os.path.exists(STATE_FILE):
            return
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            used_by_all = None
            for kw in self._keywords:
                used_for_kw = set(data.get(kw, []))
                if used_by_all is None:
                    used_by_all = used_for_kw
                else:
                    used_by_all = used_by_all.intersection(used_for_kw)
            if used_by_all:
                self._used.update(used_by_all)
        except Exception as e:
            logger.error(f"Erreur chargement used_cities: {e}")

    def has_more(self) -> bool:
        """Retourne True s'il reste des villes non essayées."""
        return self._index < len(self._cities)

    def next_batch(
        self,
        keyword: str,
        batch_size: int = 5,
    ) -> List[str]:
        """
        Retourne les prochains `batch_size` mots-clés avec ville.

        Si la ville est déjà dans le keyword (ex: "plombier Paris"),
        elle est ignorée pour éviter "plombier Paris Paris".

        Args:
            keyword:    mot-clé de base (ex: "plombier urgence")
            batch_size: nombre de variantes à retourner

        Returns:
            ["plombier urgence Lyon", "plombier urgence Marseille", ...]
        """
        result = []
        kw_lower = keyword.lower()

        while self._index < len(self._cities) and len(result) < batch_size:
            city = self._cities[self._index]
            self._index += 1

            # Éviter d'ajouter la ville si elle est déjà dans le keyword
            if city.lower() in kw_lower:
                continue
            if city in self._used:
                continue

            result.append(f"{keyword} {city}")

        return result

    def next_batch_multi(
        self,
        keywords: List[str],
        batch_size: int = 5,
    ) -> List[str]:
        """
        Comme next_batch() mais pour une liste de mots-clés.
        Ajoute la même tranche de villes à chaque keyword.

        Ex: keywords=["plombier", "chauffagiste"], batch_size=3
        → ["plombier Lyon", "plombier Marseille", "plombier Toulouse",
           "chauffagiste Lyon", "chauffagiste Marseille", ...]
        """
        cities_batch: List[str] = []
        kws_lower = [kw.lower() for kw in keywords]

        while self._index < len(self._cities) and len(cities_batch) < batch_size:
            city = self._cities[self._index]
            self._index += 1
            if city in self._used:
                continue
            cities_batch.append(city)

        result = []
        for city in cities_batch:
            for kw, kw_lower in zip(keywords, kws_lower):
                if city.lower() not in kw_lower:
                    result.append(f"{kw} {city}")

        return result

    def mark_used(self, keyword_variants: List[str]) -> None:
        """Marque des variantes comme déjà utilisées (ne les repropose pas)."""
        new_cities = set()
        for kw in keyword_variants:
            # Extraire la dernière partie (la ville) si le format est "keyword ville"
            parts = kw.rsplit(" ", 1)
            if len(parts) == 2:
                new_cities.add(parts[-1])
                self._used.add(parts[-1])
                
        # Sauvegarde persistante par mot-clé
        if self._keywords and new_cities:
            try:
                os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
                data = {}
                if os.path.exists(STATE_FILE):
                    with open(STATE_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                for kw in self._keywords:
                    existing = set(data.get(kw, []))
                    existing.update(new_cities)
                    data[kw] = list(existing)
                with open(STATE_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"Erreur sauvegarde used_cities: {e}")

    def reset(self) -> None:
        """Réinitialise le rotateur (recommence depuis la première ville)."""
        self._index = 0
        self._used.clear()

    @staticmethod
    def get_cities(country: str = "fr") -> List[str]:
        """Retourne la liste complète des villes pour un pays."""
        country = country.lower()[:2]
        return list(_CITIES.get(country, _CITIES["fr"]))
