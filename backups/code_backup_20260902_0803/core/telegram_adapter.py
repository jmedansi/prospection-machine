# -*- coding: utf-8 -*-
"""
core/telegram_adapter.py — Adaptateur vers hub_telegram/telegram_notifier.py

Usage :
    from core.telegram_adapter import notify, send_validation_request, check_pending_db
"""
import sys

from core.config import HUB_TELEGRAM

if HUB_TELEGRAM not in sys.path:
    sys.path.insert(0, HUB_TELEGRAM)

from telegram_notifier import notify, send_validation_request, check_pending_db  # noqa: E402

__all__ = ["notify", "send_validation_request", "check_pending_db"]
