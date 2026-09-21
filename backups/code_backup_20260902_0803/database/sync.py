# -*- coding: utf-8 -*-
from .connection import get_conn, logger


def log_sync(table_name: str, direction: str, rows_synced: int,
             statut: str = 'ok', erreur: str | None = None):
    """Enregistre une opération de synchronisation."""
    try:
        with get_conn() as conn:
            conn.execute("""
                INSERT INTO sync_log (table_name, direction, rows_synced, statut, erreur)
                VALUES (?, ?, ?, ?, ?)
            """, (table_name, direction, rows_synced, statut, erreur))
    except Exception as e:
        logger.error(f"log_sync → {e}")
