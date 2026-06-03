# -*- coding: utf-8 -*-
import os
import psutil
import logging

logger = logging.getLogger(__name__)

def kill_all_background_tasks():
    """
    Tue tous les scrapers et agents connus en UN SEUL scan (Ultra Rapide).
    Évite les timeouts du Dashboard.
    """
    killed = 0
    # Liste des mots-clés à repérer dans la ligne de commande
    targets = [
        'scraper/main.py', 'scraper\\main.py',
        'auditeur/main.py', 'auditeur\\main.py',
        'scraper/sniper_runner.py', 'scraper\\sniper_runner.py',
        'services/scraper_runner.py', 'services\\scraper_runner.py',
        'copywriter/main.py', 'copywriter\\main.py',
        'patchright', 'playwright', 'node.exe' # Playwright/Patchright drivers
    ]
    
    try:
        # Scan UNIQUE de tous les processus
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmd = proc.info.get('cmdline') or []
                cmd_str = " ".join(cmd).lower()
                name = (proc.info.get('name') or "").lower()
                
                # Si l'un de nos scripts ou drivers est repéré
                is_target = any(t.lower() in cmd_str for t in targets) or any(t.lower() in name for t in targets)
                
                if is_target:
                    # Ne pas tuer le dashboard lui-même !
                    if 'app.py' in cmd_str and ('flask' in cmd_str or 'python' in cmd_str):
                        continue
                        
                    logger.warning(f"[process_utils] Killing target process: {name} (PID {proc.info['pid']})")
                    proc.kill()
                    killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception as e:
        logger.error(f"[process_utils] Error during global scan: {e}")

    # Nettoyage du navigateur principal (CDP)
    try:
        from core.open_chrome import kill_chrome
        kill_chrome()
    except:
        pass
        
    return killed
