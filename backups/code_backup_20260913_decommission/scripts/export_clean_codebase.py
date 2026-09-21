# -*- coding: utf-8 -*-
"""
scripts/export_clean_codebase.py — Exporteur de Code Source Pur (SaaS Ultra)

Crée une archive ZIP ultra-légère (< 2 Mo) contenant UNIQUEMENT le code source
métier, sans dépendances .venv, sans caches, sans historique git ni profils Chrome.
Permet d'exporter, copier ou déployer le SaaS en 1 seconde.
"""
import os
import sys
import zipfile
import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Dossiers et fichiers source à inclure obligatoirement
INCLUDE_DIRS = [
    "core",
    "dashboard",
    "database",
    "services",
    "scraper",
    "sniper",
    "auditeur",
    "copywriter",
    "envoi",
    "reporter",
    "synthetiseur",
    "templates",
    "agents",
    "docs",
    "scripts"
]

INCLUDE_ROOT_FILES = [
    ".env.example",
    "requirements.txt",
    "requirements-dev.txt",
    "README.md",
    "DOCUMENTATION.md",
    "AGENTS.md",
    "CLAUDE.md",
    "ENV_SETUP.md",
    "start_machine.bat",
    "restart_dashboard.py",
    ".gitignore",
    ".antigravityignore"
]

EXCLUDE_PATTERNS = [
    "__pycache__",
    ".pytest_cache",
    "chrome_profile",
    "chrome_profiles",
    ".log",
    ".tmp",
    ".bak",
    ".pyc",
    "git_db_",
    "tmp_lead_",
    ".git",
    ".venv"
]


def export_clean_codebase(output_dir: str = r"d:\\", include_db: bool = False) -> str:
    """Génère l'archive ZIP propre du code source."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_name = f"prospection_machine_clean_source_{timestamp}.zip"
    zip_path = os.path.join(output_dir, zip_name)

    print(f"\n[EXPORT] Creation de l'archive source pure : {zip_path}")
    total_files = 0
    total_uncompressed_bytes = 0

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Fichiers racine
        for rf in INCLUDE_ROOT_FILES:
            full_path = os.path.join(ROOT, rf)
            if os.path.exists(full_path):
                zf.write(full_path, rf)
                total_files += 1
                total_uncompressed_bytes += os.path.getsize(full_path)

        # 2. Dossiers de modules
        for d in INCLUDE_DIRS:
            d_path = os.path.join(ROOT, d)
            if not os.path.exists(d_path):
                continue
            for root_dir, dirs, files in os.walk(d_path):
                # Filtrer les dossiers exclus
                dirs[:] = [sub for sub in dirs if not any(ex in sub for ex in EXCLUDE_PATTERNS)]
                for file in files:
                    if any(ex in file for ex in EXCLUDE_PATTERNS):
                        continue
                    full_file = os.path.join(root_dir, file)
                    rel_path = os.path.relpath(full_file, ROOT)
                    zf.write(full_file, rel_path)
                    total_files += 1
                    total_uncompressed_bytes += os.path.getsize(full_file)

        # 3. Base de données (optionnelle)
        if include_db:
            db_path = os.path.join(ROOT, "data", "prospection.db")
            if os.path.exists(db_path):
                zf.write(db_path, os.path.join("data", "prospection.db"))
                total_files += 1
                total_uncompressed_bytes += os.path.getsize(db_path)
        else:
            # Créer data/ avec un README
            data_readme = "Base de donnees SQLite (data/prospection.db) initialisee automatiquement au premier lancement."
            zf.writestr("data/README.md", data_readme)
            total_files += 1

    zip_size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"[EXPORT] Archive generee avec succes !")
    print(f"[EXPORT] Fichiers inclus : {total_files}")
    print(f"[EXPORT] Poids compresse : {zip_size_mb:.2f} Mo (decompresse : {total_uncompressed_bytes / (1024*1024):.2f} Mo)\n")
    return zip_path


if __name__ == "__main__":
    export_clean_codebase(include_db=False)
