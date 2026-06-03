# -*- coding: utf-8 -*-
"""
scraper/sniper/keyword_generator.py — AI Long-Tail Keyword Generator

Utilise l'API Groq (Llama 3) pour générer des mots-clés de longue traîne
très spécifiques afin d'alimenter le scheduler (auto_planner.py).
"""

import os
import re
import logging
from typing import List

logger = logging.getLogger(__name__)

def generate_long_tail(sector: str, base_keyword: str, city: str, limit: int = 5) -> List[str]:
    """
    Génère des mots-clés de longue traîne pour un secteur, mot-clé de base et ville.
    Retourne toujours une liste (vide en cas d'erreur).
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.warning("[KEYWORD_GEN] GROQ_API_KEY introuvable, impossible d'utiliser l'IA.")
        return []

    prompt = (
        f"Génère exactement {limit} intentions de recherche Google très précises ('longue traîne', minimum 3 ou 4 mots) "
        f"pour le secteur '{sector}', basés sur le service principal '{base_keyword}'.\n"
        f"Le but est de trouver des requêtes réelles de clients avec un besoin immédiat ou spécifique, "
        f"sans répéter toujours le même mot exact.\n"
        f"Exemples pour un plombier à Paris :\n"
        f"- réparation urgente fuite d'eau\n"
        f"- artisan chauffagiste pour panne chaudière\n"
        f"- rénovation salle de bain sur mesure\n\n"
        f"Important : Ne rajoute pas la ville ('{city}') à la fin de tes mots-clés, car elle sera ajoutée automatiquement par le système.\n"
        f"Ne mets aucun tiret, numéro ou puce devant. Renvoie UNIQUEMENT la liste, un par ligne. N'AJOUTE AUCUN TEXTE D'INTRODUCTION OU DE CONCLUSION."
    )

    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.7,
        )

        answer = response.choices[0].message.content.strip()
        
        # Nettoyage de la réponse
        lines = answer.split('\n')
        keywords = []
        for line in lines:
            # Enlever les puces, numéros, et espaces en trop
            clean_line = re.sub(r'^[\d\-\*\.]+\s*', '', line.strip())
            
            # Filtrer le texte conversationnel de l'IA (intro/outro)
            if not clean_line or len(clean_line) < 5 or len(clean_line) > 50:
                continue
            if clean_line.endswith(':'):
                continue
            if "voici" in clean_line.lower() or "intentions" in clean_line.lower() or "recherche" in clean_line.lower() and ":" in clean_line:
                continue
                
            keywords.append(clean_line.lower())

        logger.info(f"[KEYWORD_GEN] {len(keywords)} mots-clés générés pour {base_keyword} à {city}.")
        return keywords[:limit]

    except Exception as e:
        logger.error(f"[KEYWORD_GEN] Erreur lors de la génération avec Groq : {e}")
        return []
