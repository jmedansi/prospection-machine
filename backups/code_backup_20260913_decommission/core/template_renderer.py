# -*- coding: utf-8 -*-
"""
core/template_renderer.py — Module expert rendu de templates HTML

Point d'entrée unique pour le chargement et l'injection de variables dans les
templates email des deux pipelines (Maps et Sniper).

Usage:
    from core.template_renderer import render_template

    html = render_template("sniper/templates/email_perf.html", {
        "{{NOM}}":   "Dupont Solar",
        "{{SCORE}}": "42",
    })
"""

import logging
import re
from pathlib import Path
from typing import Union

logger = logging.getLogger(__name__)


def render_template(
    path: Union[str, Path],
    variables: dict[str, str],
) -> str:
    """
    Charge un template HTML et injecte les variables.

    Args:
        path:      Chemin absolu ou relatif (depuis la racine du projet) du template.
        variables: Dict {placeholder: valeur}, ex: {"{{NOM}}": "Jean Dupont"}.

    Returns:
        HTML avec toutes les variables substituées.

    Raises:
        FileNotFoundError: Si le template est introuvable.
    """
    path = Path(path)
    if not path.is_absolute():
        # Résolution depuis la racine du projet (2 niveaux au-dessus de core/)
        root = Path(__file__).parent.parent
        path = root / path

    if not path.exists():
        raise FileNotFoundError(f"Template introuvable : {path}")

    html = path.read_text(encoding="utf-8")

    for placeholder, value in variables.items():
        html = html.replace(placeholder, str(value) if value is not None else "")

    logger.debug(f"[template_renderer] rendu {path.name} — {len(variables)} variables")
    return html


def extract_subject(html: str) -> str:
    """
    Extrait le sujet de l'email depuis la balise <title> du template.
    Retourne un sujet par défaut si absent.
    """
    match = re.search(r"<title>([^<]+)</title>", html, re.IGNORECASE)
    return match.group(1).strip() if match else "Rapport d'analyse de votre site"
