# -*- coding: utf-8 -*-
"""
core/open_chrome.py — Profil Chrome du projet

Source de vérité unique pour l'ouverture de Chrome.
Pour changer de profil, modifier CHROME_PROFILE_DIR ici — tous les modules suivent.

Usage direct :  python core/open_chrome.py
Usage module  : from core.open_chrome import launch_chrome, CHROME_PATH, CHROME_PROFILE_DIR
"""

import os
import subprocess
import psutil
import logging

logger = logging.getLogger(__name__)

CHROME_PATH        = "C:/Program Files/Google/Chrome/Application/chrome.exe"
CHROME_PROFILE_DIR = os.path.join(
    os.environ.get("USERPROFILE", "C:\\Users\\jmeda"),
    "AppData", "Local", "Google", "Chrome", "User Data", "Profile 1"
)

CHROME_BASE_ARGS = [
    "--remote-debugging-port=9222",
    "--no-first-run",
    "--no-default-browser-check",
    "--no-sandbox",
    "--start-maximized",
    "--disable-blink-features=AutomationControlled",
    "--process-per-site",
    "--renderer-process-limit=2",
    "--disable-features=TranslateUI,ChromeWhatsNewUI,InterestFeedContentSuggestions",
    "--disable-background-networking",
]


def kill_chrome(only_project: bool = True):
    """
    Tue les processus Chrome.
    Si only_project=True, ne tue que ceux utilisant le port 9222 ou le profil du projet.
    """
    target_port = "9222"
    # Normalisation du chemin pour la comparaison
    target_profile = CHROME_PROFILE_DIR.replace("\\", "/").lower()
    
    killed_count = 0
    # On récupère d'abord tous les candidats pour éviter les erreurs de modification de liste
    candidates = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['name'] == 'chrome.exe':
                cmdline_list = proc.info.get('cmdline') or []
                cmdline_str = " ".join(cmdline_list).lower().replace("\\", "/")
                
                is_target = False
                if f"--remote-debugging-port={target_port}" in cmdline_str:
                    is_target = True
                elif target_profile in cmdline_str:
                    is_target = True
                elif "--headless" in cmdline_str and "user-data-dir" not in cmdline_str:
                    # Probablement un processus Playwright orphelin sans profil utilisateur standard
                    is_target = True
                
                if not only_project or is_target:
                    candidates.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
            
    for p in candidates:
        try:
            # On tue récursivement les enfants d'abord (renderers, gpu process, etc.)
            for child in p.children(recursive=True):
                try:
                    child.kill()
                except:
                    pass
            
            logger.info(f"[kill_chrome] Suppression du processus racine {p.pid}")
            p.kill()
            killed_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    
    if killed_count > 0:
        import time
        time.sleep(1)
        print(f"Nettoyage : {killed_count} processus Chrome racines et leurs enfants ont été fermés.")

def launch_chrome(extra_args: list = None, force_restart: bool = False):
    """Lance Chrome avec le profil du projet et le port CDP 9222."""
    if force_restart:
        kill_chrome()
    
    args = [CHROME_PATH, f"--user-data-dir={CHROME_PROFILE_DIR}"] + CHROME_BASE_ARGS
    if extra_args:
        args += extra_args
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"Chrome ouvert avec le profil: {CHROME_PROFILE_DIR}")
    return proc


if __name__ == "__main__":
    launch_chrome()
