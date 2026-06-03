import psutil
import os
import time

project_profile = r"d:\prospection-machine\data\chrome_profile".lower().replace("\\", "/")
target_port = "9222"

print(f"Nettoyage sécurisé des processus Chrome liés au projet...")
print(f"Profil cible : {project_profile}")

killed_count = 0

for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
    try:
        if proc.info['name'] == 'chrome.exe':
            cmdline_list = proc.info.get('cmdline') or []
            cmdline_str = " ".join(cmdline_list).lower().replace("\\", "/")
            
            # Criteres de selection :
            # 1. Utilise le port 9222
            # 2. Utilise le profil du projet
            # 3. Est headless (Playwright orphelin) - on assume que les headless sont lies au projet s'ils n'ont pas de profil utilisateur standard
            
            is_project_cdp = f"--remote-debugging-port={target_port}" in cmdline_str
            is_project_profile = project_profile in cmdline_str
            is_headless = "--headless" in cmdline_str
            
            # Pour le headless, on verifie qu'il n'appartient pas a un profil utilisateur standard du systeme
            # (pour eviter de tuer des trucs comme Teams, Discord ou autre qui utilisent des webviews chrome)
            is_suspicious_headless = is_headless and "google/chrome" in cmdline_str and "user data" not in cmdline_str
            
            if is_project_cdp or is_project_profile or is_suspicious_headless:
                print(f"Killing process {proc.info['pid']} : {cmdline_str[:100]}...")
                # Kill children first
                for child in proc.children(recursive=True):
                    try: child.kill()
                    except: pass
                proc.kill()
                killed_count += 1
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        continue

if killed_count > 0:
    print(f"Nettoyage terminé : {killed_count} processus fermés.")
else:
    print("Aucun processus lié au projet trouvé.")
