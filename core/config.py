import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
_loaded = False

def ensure_env():
    global _loaded
    if not _loaded:
        load_dotenv(ROOT / ".env")
        _loaded = True

HUB_TELEGRAM = os.getenv('HUB_TELEGRAM_PATH', 'D:/hub_telegram/_system_hub')

def set_env_var(key, value):
    """Met à jour une variable dans le fichier .env."""
    ensure_env()
    env_path = ROOT / ".env"
    lines = []
    found = False
    if env_path.exists():
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith(f"{key}="):
                    lines.append(f'{key}="{value}"\n')
                    found = True
                else:
                    lines.append(line)
    if not found:
        lines.append(f'{key}="{value}"\n')
    
    with open(env_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    os.environ[key] = value
