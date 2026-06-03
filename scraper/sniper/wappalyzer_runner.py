# -*- coding: utf-8 -*-
"""
scraper/sniper/wappalyzer_runner.py — Wrapper Python pour Wappalyzer (NPM local)

Appelle wappalyzer_check.js en sous-processus Node.js.
Retourne un dict normalisé : {cms, cdn, ecommerce, server, technologies, error}

Prérequis :
    npm install wappalyzer      (dans le dossier du projet ou globalement)

En cas d'absence de Node.js ou du package, retourne un dict vide gracieusement.
"""

import json
import logging
import os
import subprocess
import threading
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_JS_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wappalyzer_check.js")

# Cache in-process pour éviter les appels redondants sur le même domaine
_cache: Dict[str, dict] = {}

# Sémaphore : 1 seul Chromium Wappalyzer à la fois (évite N fenêtres Chrome en parallèle)
_wap_lock = threading.Semaphore(1)


def _find_node() -> Optional[str]:
    """Trouve l'exécutable Node.js sur le système."""
    candidates = ["node", "node.exe", r"C:\Program Files\nodejs\node.exe"]
    for c in candidates:
        try:
            result = subprocess.run(
                [c, "--version"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return c
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return None


def analyze(url: str, timeout: int = 30) -> Dict:
    """
    Analyse la stack technologique d'une URL via Wappalyzer NPM.

    Args:
        url:     URL complète (ex: "https://example.com")
        timeout: secondes avant abandon

    Returns:
        {
            "cms":         str | None,   # Ex: "WordPress", "PrestaShop"
            "cdn":         str | None,   # Ex: "Cloudflare", "Sucuri"
            "ecommerce":   str | None,   # Ex: "WooCommerce"
            "server":      str | None,   # Ex: "Apache", "nginx"
            "technologies": [str],       # Liste brute
            "error":       str | None,
        }
    """
    empty = {"cms": None, "cdn": None, "ecommerce": None, "server": None,
             "technologies": [], "error": None}

    # Cache hit
    if url in _cache:
        return _cache[url]

    node = _find_node()
    if not node:
        logger.warning("Node.js introuvable — analyse Wappalyzer ignorée")
        return {**empty, "error": "Node.js non disponible"}

    if not os.path.exists(_JS_SCRIPT):
        logger.error(f"Script Wappalyzer introuvable : {_JS_SCRIPT}")
        return {**empty, "error": "wappalyzer_check.js manquant"}

    with _wap_lock:
        try:
            proc = subprocess.run(
                [node, _JS_SCRIPT, url],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=os.path.dirname(_JS_SCRIPT),
            )

            stdout = proc.stdout.strip()
            if not stdout:
                logger.warning(f"Wappalyzer : sortie vide pour {url} (stderr: {proc.stderr[:200]})")
                return {**empty, "error": "Pas de sortie"}

            result = json.loads(stdout)
            _cache[url] = result
            return result

        except subprocess.TimeoutExpired:
            logger.warning(f"Wappalyzer timeout ({timeout}s) pour {url}")
            return {**empty, "error": f"Timeout {timeout}s"}
        except json.JSONDecodeError as e:
            logger.error(f"Wappalyzer JSON invalide pour {url}: {e}")
            return {**empty, "error": "JSON invalide"}
        except Exception as e:
            logger.error(f"Wappalyzer erreur pour {url}: {e}")
            return {**empty, "error": str(e)}
