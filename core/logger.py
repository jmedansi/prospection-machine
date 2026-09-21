# -*- coding: utf-8 -*-
"""
core/logger.py — Centralized Rotating Logger for Prospection Machine
Empêche les fichiers de log de grossir indéfiniment et garantit une rotation propre.
"""
import os
import logging
from logging.handlers import RotatingFileHandler
from core.config import ROOT

LOGS_DIR = os.path.join(ROOT, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

DEFAULT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
MAX_BYTES = 5 * 1024 * 1024  # 5 MB
BACKUP_COUNT = 3


def get_logger(name: str = "prospection_machine", log_file: str = "app.log", level: int = logging.INFO) -> logging.Logger:
    """Retourne un logger configuré avec rotation automatique."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Éviter d'ajouter plusieurs handlers si déjà configuré
    if not logger.handlers:
        # File Handler avec rotation
        file_path = os.path.join(LOGS_DIR, log_file)
        file_handler = RotatingFileHandler(
            file_path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
        )
        file_handler.setLevel(level)
        file_formatter = logging.Formatter(DEFAULT_FORMAT)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        # Stream Handler (Console)
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.WARNING)
        stream_formatter = logging.Formatter(DEFAULT_FORMAT)
        stream_handler.setFormatter(stream_formatter)
        logger.addHandler(stream_handler)

    return logger
