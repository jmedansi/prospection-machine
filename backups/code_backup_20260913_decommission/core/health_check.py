import os
import sys
import sqlite3
from pathlib import Path
from typing import Dict, Any

# Assurer que la racine du projet est dans sys.path
ROOT_PATH = str(Path(__file__).parent.parent)
if ROOT_PATH not in sys.path:
    sys.path.insert(0, ROOT_PATH)

from core.config import ensure_env, ROOT, HUB_TELEGRAM

ensure_env()


def run_system_health_check() -> Dict[str, Any]:
    """Exécute un audit complet de l'environnement SaaS."""
    report = {
        "status": "healthy",
        "database": {"ok": False, "details": ""},
        "directories": {"ok": True, "details": []},
        "services": {},
        "env_vars": {}
    }

    # 1. Base de données
    db_path = os.path.join(ROOT, "data", "prospection.db")
    if not os.path.exists(db_path):
        report["database"] = {"ok": False, "details": f"Fichier {db_path} introuvable"}
        report["status"] = "degraded"
    else:
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("PRAGMA integrity_check;")
            integrity = cur.fetchone()[0]
            leads_count = cur.execute("SELECT count(*) FROM leads_bruts").fetchone()[0]
            audits_count = cur.execute("SELECT count(*) FROM leads_audites").fetchone()[0]
            emails_count = cur.execute("SELECT count(*) FROM emails_envoyes").fetchone()[0]
            conn.close()
            report["database"] = {
                "ok": integrity == "ok",
                "integrity": integrity,
                "leads_count": leads_count,
                "audits_count": audits_count,
                "emails_count": emails_count,
                "size_mb": round(os.path.getsize(db_path) / (1024 * 1024), 2)
            }
        except Exception as e:
            report["database"] = {"ok": False, "details": str(e)}
            report["status"] = "degraded"

    # 2. Dossiers essentiels
    for sub in ["data", "logs", "scripts", "templates", "dashboard"]:
        dir_path = os.path.join(ROOT, sub)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
            report["directories"]["details"].append(f"Créé {sub}/")

    # 3. Variables d'environnement & Services
    env_checks = [
        ("RESEND_API_KEY", "Emailing (Resend)", True),
        ("BREVO_API_KEY", "Emailing Fallback (Brevo)", False),
        ("GROQ_API_KEY", "LLM Fast (Groq)", False),
        ("GEMINI_API_KEY", "LLM Vision/Advanced (Gemini)", False),
        ("HUB_TELEGRAM_PATH", "Validation Telegram", False),
    ]

    for var, label, critical in env_checks:
        val = os.getenv(var)
        is_set = bool(val and len(val.strip()) > 4)
        report["env_vars"][var] = {
            "label": label,
            "set": is_set,
            "critical": critical
        }
        if critical and not is_set:
            report["status"] = "warning"

    # 4. Hub Telegram local
    report["services"]["telegram_hub"] = {
        "ok": os.path.exists(HUB_TELEGRAM),
        "path": HUB_TELEGRAM
    }

    return report


if __name__ == "__main__":
    import json
    res = run_system_health_check()
    print(json.dumps(res, indent=2, ensure_ascii=False))
