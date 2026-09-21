# -*- coding: utf-8 -*-
"""
backup_db.py - Sauvegarde automatique de la base de donnees SQLite

Fonctionnement :
  1. Copie horodatee locale dans backups/daily/ (garde les 7 derniers)
  2. Commit + push Git automatique

Usage manuel :
  python backup_db.py
  python backup_db.py --no-git    (backup local uniquement)
"""

import os
import sys

# Forcer UTF-8 pour eviter les problemes d'encodage Windows
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import shutil
import logging
import argparse
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

# --- Config ---
ROOT = Path(__file__).parent
DB_PATH = ROOT / "data" / "prospection.db"
BACKUP_DIR = ROOT / "backups" / "daily"
MAX_BACKUPS = 7  # Garder les 7 derniers backups locaux

logger = logging.getLogger(__name__)


def _count_db(db_path: Path) -> dict:
    """Retourne le nombre de lignes des tables principales."""
    counts = {}
    try:
        conn = sqlite3.connect(str(db_path))
        for table in ['leads_bruts', 'leads_audites', 'emails_envoyes']:
            try:
                c = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                counts[table] = c[0] if c else 0
            except Exception:
                counts[table] = 0
        conn.close()
    except Exception:
        pass
    return counts


def backup_local() -> Path:
    """Cree une copie horodatee de la DB dans backups/daily/."""
    if not DB_PATH.exists():
        logger.error(f"[BACKUP] DB introuvable : {DB_PATH}")
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"prospection_{ts}.db"

    try:
        # sqlite3.backup() = copie propre meme si la DB est ouverte
        src_conn = sqlite3.connect(str(DB_PATH))
        dst_conn = sqlite3.connect(str(dest))
        src_conn.backup(dst_conn)
        dst_conn.close()
        src_conn.close()

        size_mb = dest.stat().st_size / 1024 / 1024
        counts = _count_db(dest)
        logger.info(
            f"[BACKUP] Local OK -> {dest.name} ({size_mb:.2f} MB) | "
            f"leads_bruts={counts.get('leads_bruts', '?')} | "
            f"leads_audites={counts.get('leads_audites', '?')}"
        )
        print(
            f"[BACKUP] OK {dest.name} ({size_mb:.2f} MB) - "
            f"leads_bruts={counts.get('leads_bruts', '?')}, "
            f"emails={counts.get('emails_envoyes', '?')}"
        )
        return dest

    except Exception as e:
        logger.error(f"[BACKUP] Erreur copie locale : {e}")
        print(f"[BACKUP] ERREUR copie locale : {e}")
        return None


def cleanup_old_backups():
    """Supprime les backups locaux au-dela de MAX_BACKUPS."""
    if not BACKUP_DIR.exists():
        return
    backups = sorted(
        BACKUP_DIR.glob("prospection_*.db"),
        key=lambda f: f.stat().st_mtime
    )
    to_delete = backups[:-MAX_BACKUPS] if len(backups) > MAX_BACKUPS else []
    for old in to_delete:
        try:
            old.unlink()
            logger.info(f"[BACKUP] Ancien backup supprime : {old.name}")
        except Exception as e:
            logger.warning(f"[BACKUP] Impossible de supprimer {old.name} : {e}")
    if to_delete:
        print(f"[BACKUP] {len(to_delete)} ancien(s) backup(s) supprime(s)")


def backup_git(local_backup_path: Path = None) -> bool:
    """Commit + push de toute la machine (base de données, sauvegardes et code) sur GitHub."""
    try:
        counts = _count_db(DB_PATH)
        msg = (
            f"Backup automatique Machine & DB {datetime.now().strftime('%Y-%m-%d %H:%M')} - "
            f"leads={counts.get('leads_bruts', '?')}, "
            f"audits={counts.get('leads_audites', '?')}, "
            f"emails={counts.get('emails_envoyes', '?')}"
        )

        # Stage toutes les modifications et nouveaux fichiers (respecte le .gitignore mis à jour)
        cmds = [
            ['git', 'add', '.'],
            ['git', 'commit', '-m', msg],
            ['git', 'push'],
        ]

        for cmd in cmds:
            result = subprocess.run(
                cmd,
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            if result.returncode != 0:
                stdout = result.stdout or ''
                stderr = result.stderr or ''
                if 'nothing to commit' in stdout or 'nothing to commit' in stderr:
                    logger.info("[BACKUP] Git: aucun changement à committer")
                    print("[BACKUP] Git: aucun changement depuis le dernier backup")
                    return True
                logger.error(f"[BACKUP] Git '{' '.join(cmd)}' erreur : {stderr}")
                print(f"[BACKUP] WARN Git erreur ({' '.join(cmd[:2])}) : {stderr.strip()}")
                return False

        logger.info(f"[BACKUP] Git push OK : {msg}")
        print(f"[BACKUP] Git push OK")
        return True

    except Exception as e:
        logger.error(f"[BACKUP] Git erreur : {e}")
        print(f"[BACKUP] ERREUR Git : {e}")
        return False


def run_backup(git: bool = True) -> bool:
    """Point d'entree principal - appele par le scheduler ou manuellement."""
    print(f"\n{'='*55}")
    print(f"  BACKUP DB - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*55}")

    # 1. Backup local
    dest = backup_local()
    if dest is None:
        return False

    # 2. Nettoyage anciens backups
    cleanup_old_backups()

    # 3. Git push
    if git:
        backup_git(dest)

    print(f"{'='*55}\n")
    return True


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    parser = argparse.ArgumentParser(description="Backup automatique de la base de donnees")
    parser.add_argument("--no-git", action="store_true", help="Backup local uniquement, sans git push")
    args = parser.parse_args()

    success = run_backup(git=not args.no_git)
    sys.exit(0 if success else 1)
