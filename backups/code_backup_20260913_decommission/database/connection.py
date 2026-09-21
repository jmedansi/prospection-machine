# -*- coding: utf-8 -*-
import sqlite3
import json
import logging
from pathlib import Path
from core.config import ensure_env

# Initialiser l'environnement
ensure_env()

# --- Chemin vers la base de données ---
DB_PATH = Path(__file__).parent.parent / "data" / "prospection.db"

# --- Logging ---
logging.basicConfig(
    filename=str(Path(__file__).parent.parent / "errors.log"),
    level=logging.ERROR,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_conn() -> sqlite3.Connection:
    """Retourne une connexion SQLite avec row_factory et WAL activé."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # Lectures et écritures simultanées
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _serialize_json(data: dict, keys: list) -> dict:
    """Sérialise les champs de type liste en JSON string."""
    result = dict(data)
    for key in keys:
        if isinstance(result.get(key), (list, dict)):
            result[key] = json.dumps(result[key], ensure_ascii=False)
    return result


def _deserialize_json(row: dict, keys: list) -> dict:
    """Désérialise les champs JSON string en objets Python."""
    result = dict(row)
    for key in keys:
        val = result.get(key)
        if val and isinstance(val, str):
            try:
                result[key] = json.loads(val)
            except Exception:
                pass
    return result
