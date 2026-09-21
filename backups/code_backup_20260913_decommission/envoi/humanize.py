# -*- coding: utf-8 -*-
"""
envoi/humanize.py — passe d'humanisation IA sur un email généré.

Transforme un texte rendu depuis template (mot-à-mot, lissé) en formulation
naturelle à la main : variance de style, intonation humaine, pas de ton
pitch/automatisé. On préserve STRICTEMENT les faits (noms, liens, chiffres).

Fonctionne via config_manager.handle_llm_call (Groq). En l'absence de clé ou sur
erreur LLM → retour au texte d'origine (jamais d'échec d'envoi pour la passe IA).
"""
import json
import logging
import re

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Tu es un commercial senior qui rédige des emails de prospection à la main, "
    "avec naturel et humilité. Tu réécris les textes fournis pour qu'ils sonnent "
    "personnels et non-automatisés : phrases variées, aucune répétition de template, "
    "aucun compliment exagéré, aucun urgentisme, fautes de marketing bannies "
    "(\"chez nous\", \"solutions innovantes\", etc.)."
)

PROMPT_TEMPLATE = (
    "Voici un email de prospection déjà rédigé pour un commerce local. "
    "Réécris-le pour qu'il semble écrit à la main par un consultant, en conservant "
    "EXACTEMENT : l'objet, le nom de l'entreprise, les liens, l'adresse de site, tous "
    "les chiffres, les noms propres et la signature. Réponds uniquement au format JSON "
    "avec les clés \"objet\" et \"corps\". Ne rien inventer.\n\n"
    "## OBJET\n{objet}\n\n"
    "## CORPS\n{corps}\n\n"
    "## JSON"
)


def humanize_email(objet: str, corps: str, prospect: dict = None, dry_run: bool = False) -> dict:
    """Réécrit à la main objet + corps. Retourne {'objet', 'corps', 'humanise': bool}."""
    result = {'objet': objet, 'corps': corps, 'humanise': False}

    if dry_run:
        return result

    if not objet and not corps:
        return result

    if not _llm_available():
        return result

    prompt = PROMPT_TEMPLATE.format(objet=objet or '', corps=corps or '')
    try:
        from config_manager import handle_llm_call
        raw = (handle_llm_call(prompt, system=SYSTEM_PROMPT) or '').strip()
        parsed = extract_json(raw)
        if not parsed:
            logger.warning("[humanize] sortie LLM non parsable — template d'origine")
            return result
        n_objet = (parsed.get('objet') or '').strip()
        n_corps = (parsed.get('corps') or '').strip()
        outcome = {
            'objet': n_objet or objet,
            'corps': n_corps or corps,
            'humanise': bool(n_objet and n_corps),
        }
        # garde-fou : ne jamais perdre l'objet ou le corps
        if not outcome['humanise'] or len(n_corps) < 20:
            return result
        return outcome
    except Exception as e:
        logger.error("[humanize] %s — template d'origine", e)
        return result


def _llm_available() -> bool:
    import os
    from core.config import ensure_env
    ensure_env()
    return bool(os.getenv('GROQ_API_KEY', '').strip()
                or os.getenv('GROQ_API_KEY_2', '').strip())


def extract_json(raw: str) -> dict:
    """Extrait le premier objet JSON d'une réponse LLM (tolérant aux fioritures)."""
    if not raw:
        return {}
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start = text.find('{')
    end = text.rfind('}')
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            pass
    return {}