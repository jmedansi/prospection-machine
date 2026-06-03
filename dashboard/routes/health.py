# -*- coding: utf-8 -*-
"""
dashboard/routes/health.py — Route GET /api/health

Vérifie l'état de tous les composants critiques du système et retourne un
rapport structuré. Utilisé par le dashboard pour l'indicateur de santé.

Catégories de checks :
  - database   : connexion SQLite + tables
  - agents     : importabilité de chaque agent
  - env        : clés API présentes (sans les révéler)
  - filesystem : fichiers et dossiers requis
"""
import os
import time
import importlib
from flask import Blueprint, jsonify

health_bp = Blueprint("health", __name__)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _check(name: str, category: str, fn) -> dict:
    """Exécute un check et retourne un dict normalisé."""
    t0 = time.monotonic()
    try:
        status, message = fn()
    except Exception as e:
        status, message = "fail", str(e)
    return {
        "name":        name,
        "category":    category,
        "status":      status,          # "ok" | "warn" | "fail"
        "message":     message,
        "duration_ms": int((time.monotonic() - t0) * 1000),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Checks — Database
# ─────────────────────────────────────────────────────────────────────────────

def chk_db_connect():
    from database.connection import get_conn
    with get_conn() as conn:
        conn.execute("SELECT 1").fetchone()
    return "ok", "Connexion SQLite OK"


def chk_db_tables():
    from database.connection import get_conn
    required = ["leads_bruts", "leads_audites", "emails_envoyes"]
    with get_conn() as conn:
        existing = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    missing = [t for t in required if t not in existing]
    if missing:
        return "fail", f"Tables manquantes : {', '.join(missing)}"
    return "ok", f"{len(required)} tables présentes"


def chk_db_counts():
    from database.connection import get_conn
    with get_conn() as conn:
        leads   = conn.execute("SELECT COUNT(*) FROM leads_bruts").fetchone()[0]
        audits  = conn.execute("SELECT COUNT(*) FROM leads_audites").fetchone()[0]
        emails  = conn.execute("SELECT COUNT(*) FROM emails_envoyes").fetchone()[0]
    return "ok", f"{leads} leads · {audits} audits · {emails} emails"


# ─────────────────────────────────────────────────────────────────────────────
# Checks — Agents
# ─────────────────────────────────────────────────────────────────────────────

def _make_agent_check(module_path: str, singleton_name: str):
    def fn():
        mod = importlib.import_module(module_path)
        agent = getattr(mod, singleton_name)
        return "ok", f"{agent.name} importé"
    return fn


# ─────────────────────────────────────────────────────────────────────────────
# Checks — Env vars
# ─────────────────────────────────────────────────────────────────────────────

def _make_env_check(var: str, label: str, optional: bool = False):
    def fn():
        val = os.getenv(var, "")
        if val:
            masked = val[:4] + "****" + val[-2:] if len(val) > 8 else "****"
            return "ok", f"{label} configurée ({masked})"
        if optional:
            return "warn", f"{label} absente (optionnel)"
        return "fail", f"{label} manquante — variable : {var}"
    return fn


# ─────────────────────────────────────────────────────────────────────────────
# Checks — Filesystem
# ─────────────────────────────────────────────────────────────────────────────

def chk_db_file():
    path = os.path.join(ROOT, "data", "prospection.db")
    if not os.path.isfile(path):
        return "fail", f"Fichier DB introuvable : {path}"
    size_kb = os.path.getsize(path) // 1024
    return "ok", f"prospection.db ({size_kb} KB)"


def chk_reports_dir():
    path = os.path.join(ROOT, "reporter", "reports")
    if not os.path.isdir(path):
        return "warn", "Dossier reporter/reports/ absent (aucun rapport généré)"
    count = sum(1 for d in os.listdir(path) if os.path.isdir(os.path.join(path, d)))
    return "ok", f"{count} rapport(s) local/locaux"


def chk_reporter_module():
    path = os.path.join(ROOT, "reporter")
    if not os.path.isdir(path):
        return "fail", "Module reporter/ introuvable"
    return "ok", "Module reporter/ présent"

def chk_browser_status():
    """Vérifie si Chrome est actif et répond au CDP."""
    from core.browser import _port_open, _is_cdp_responding
    if not _port_open():
        return "fail", "Chrome non détecté sur le port 9222"
    if not _is_cdp_responding():
        return "warn", "Chrome présent mais CDP ne répond pas (zombie)"
    return "ok", "Navigateur Chrome opérationnel"

# ─────────────────────────────────────────────────────────────────────────────
# Route
# ─────────────────────────────────────────────────────────────────────────────

CHECKS = [
    # Database
    ("Connexion SQLite",    "database",   chk_db_connect),
    ("Tables requises",     "database",   chk_db_tables),
    ("Contenu DB",          "database",   chk_db_counts),
    ("Fichier .db",         "filesystem", chk_db_file),
    ("Navigateur Chrome",   "browser",    chk_browser_status),

    # Filesystem
    ("Dossier rapports",    "filesystem", chk_reports_dir),
    ("Module reporter",     "filesystem", chk_reporter_module),

    # Agents
    ("Agent scraper",       "agents",     _make_agent_check("agents.scraper",      "scraper_agent")),
    ("Agent enrichisseur",  "agents",     _make_agent_check("agents.enrichisseur", "enrichisseur_agent")),
    ("Agent auditeur",      "agents",     _make_agent_check("agents.auditeur",     "auditeur_agent")),
    ("Agent éditeur",       "agents",     _make_agent_check("agents.editeur",      "editeur_agent")),
    ("Agent publieur",      "agents",     _make_agent_check("agents.publieur",     "publieur_agent")),
    ("Agent rédacteur",     "agents",     _make_agent_check("agents.redacteur",    "redacteur_agent")),
    ("Agent expéditeur",    "agents",     _make_agent_check("agents.expediteur",   "expediteur_agent")),
    ("Agent tracker",       "agents",     _make_agent_check("agents.tracker",      "tracker_agent")),

    # Env vars
    ("Resend API key",      "env",        _make_env_check("RESEND_API_KEY",    "Resend")),

    ("GitHub token",        "env",        _make_env_check("GITHUB_TOKEN",      "GitHub",   optional=True)),
    ("Brevo API key",       "env",        _make_env_check("BREVO_API_KEY",     "Brevo",    optional=True)),
]


@health_bp.route("/api/health")
def api_health():
    """
    Retourne l'état de tous les composants critiques.

    Response:
        {
          "status":  "ok" | "degraded" | "critical",
          "score":   {"ok": N, "warn": N, "fail": N, "total": N},
          "checks":  [{name, category, status, message, duration_ms}, ...]
        }
    """
    results = [_check(name, cat, fn) for name, cat, fn in CHECKS]

    counts = {"ok": 0, "warn": 0, "fail": 0}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    if counts["fail"] > 0:
        overall = "critical"
    elif counts["warn"] > 0:
        overall = "degraded"
    else:
        overall = "ok"

    return jsonify({
        "status":  overall,
        "score":   {**counts, "total": len(results)},
        "checks":  results,
    })


@health_bp.route("/api/health/restart-browser", methods=["POST"])
def restart_browser_route():
    """Force le redémarrage de Chrome via l'API."""
    try:
        from core.browser import _ensure_chrome
        _ensure_chrome(force_restart=True)
        return jsonify({"status": "ok", "message": "Navigateur redémarré avec succès"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@health_bp.route("/api/logs")
def get_logs():
    """Retourne les 200 dernières lignes du fichier errors.log."""
    log_path = os.path.join(ROOT, "errors.log")
    if not os.path.exists(log_path):
        return jsonify({"logs": "Aucun fichier de log trouvé à la racine."})
    
    try:
        # On lit les dernières lignes de manière efficace
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            # Pour un gros fichier, on ne veut pas tout charger. 
            # Mais 17MB ça va encore pour readlines() occasionnel.
            lines = f.readlines()
            last_lines = lines[-200:]
            return jsonify({
                "logs": "".join(last_lines),
                "total_lines": len(lines),
                "file_size": os.path.getsize(log_path)
            })
    except Exception as e:
        return jsonify({"logs": f"Erreur lors de la lecture des logs: {str(e)}"}), 500
