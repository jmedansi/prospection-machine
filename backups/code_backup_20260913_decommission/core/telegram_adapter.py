# -*- coding: utf-8 -*-
"""
core/telegram_adapter.py — Adaptateur vers hub_telegram/telegram_notifier.py

Usage :
    from core.telegram_adapter import notify, send_validation_request, check_pending_db
"""
import os
import sys
import logging

logger = logging.getLogger(__name__)

from core.config import HUB_TELEGRAM

# Ajouter HUB_TELEGRAM et son sous-dossier _system_hub au sys.path
for p in (HUB_TELEGRAM, os.path.join(HUB_TELEGRAM, "_system_hub")):
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)

try:
    from telegram_notifier import notify, send_validation_request, check_pending_db  # noqa: E402
except ImportError as e:
    logger.warning(f"[telegram_adapter] telegram_notifier introuvable ({e}) — utilisation des fallbacks no-op")
    def notify(message: str, **kwargs):
        logger.info(f"[Telegram Mock] {message}")
        return False
    def send_validation_request(*args, **kwargs):
        logger.info(f"[Telegram Mock] Validation request: {args}")
        return False
    def check_pending_db(*args, **kwargs):
        return []

__all__ = ["notify", "send_validation_request", "check_pending_db"]
