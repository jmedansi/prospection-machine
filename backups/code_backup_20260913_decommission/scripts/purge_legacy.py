# -*- coding: utf-8 -*-
"""
scripts/purge_legacy.py — purge du pipeline 1 (legacy) AVANT bascule v2.

À exécuter depuis la racine :  C:\\Python314\\python.exe scripts/purge_legacy.py --yes

Séquence :
    1. Backup horodaté de `data/prospection.db` -> `data/backup/prospection_<ts>.db`
       (échec -> on ne continue PAS)
    2. Vérification des tables v2 restantes (objectifs/prospects/...)
    3. DROP des tables legacy (idempotent)
    4. Rapport avant / après

Gardées : v2 (objectifs, prospects, prospect_events, suppression_list, mailboxes,
sequence_templates) + config/logs (planning_settings, system_logs, ia_executions,
sync_log, async_tasks). `--purge-config-pragma` supprime aussi planning_settings.
"""
import argparse
import os
import sqlite3
import sys
from datetime import datetime

LEGACY_TABLES = [
    # pipeline email 1 (le corps du legacy)
    "leads_bruts", "leads_audites", "emails_envoyes", "email_events",
    "email_sequences", "planned_campaigns", "campagnes",
    # dépendances / métadonnées métier
    "scraping_priorities", "scheduled_batches", "review_machine_runs",
    "lead_lists", "lead_list_items", "lead_categories",
]

KEEP_V2 = ("objectifs", "prospects", "prospect_events", "suppression_list",
           "mailboxes", "sequence_templates")


def main() -> int:
    ap = argparse.ArgumentParser(description="Purge du legacy (backup d'abord).")
    ap.add_argument("--yes", action="store_true", help="confirmer la purge")
    ap.add_argument("--db", default=os.path.join("data", "prospection.db"),
                    help="chemin de la base (défaut data/prospection.db)")
    ap.add_argument("--purge-config-pragma", action="store_true",
                    help="supprime aussi planning_settings")
    args = ap.parse_args()

    if not args.yes:
        print("Refus : ajouter --yes pour confirmer la purge.")
        return 2

    db_path = os.path.abspath(args.db)
    if not os.path.exists(db_path):
        print(f"Base introuvable : {db_path}")
        return 2

    backup_dir = os.path.join(os.path.dirname(db_path), "backup")
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"prospection_{ts}.db")
    # La base est en mode WAL : copie de fichier (@shutil.copy2) PERDRAIT les
    # dernières transactions. On passe par l'API de backup SQLite (cohérente).
    try:
        src = sqlite3.connect(db_path)
        dst = sqlite3.connect(backup_path)
        src.backup(dst)
        dst.close()
        src.close()
    except Exception as e:
        print(f"ECHEC backup (pas de purge) : {e}")
        return 1
    if not os.path.exists(backup_path) or os.path.getsize(backup_path) == 0:
        print("ECHEC backup : base copiée vide/introuvable, on ne purge PAS.")
        return 1
    print(f"[1/3] Backup OK -> {backup_path} "
          f"({os.path.getsize(backup_path)} octets)")

    conn = sqlite3.connect(db_path)
    existing = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    missing_v2 = [t for t in KEEP_V2 if t not in existing]
    if missing_v2:
        print(f"ABANDON : tables v2 manquantes {missing_v2} — "
              "migrate_v2_schema() pas exécutée ?")
        conn.close()
        return 1

    to_drop = [t for t in LEGACY_TABLES if t in existing]
    if args.purge_config_pragma and "planning_settings" in existing:
        to_drop.append("planning_settings")

    if not to_drop:
        print("[2/3] Aucune table legacy à purger.")
    else:
        for t in to_drop:
            conn.execute(f"DROP TABLE IF EXISTS {t}")
        conn.commit()
        print(f"[2/3] {len(to_drop)} tables legacy purgées : {', '.join(to_drop)}")

    remaining = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()

    print("[3/3] Tables restantes :", ", ".join(sorted(remaining)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

