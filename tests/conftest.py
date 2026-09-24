# -*- coding: utf-8 -*-
"""
tests/conftest.py — isolation globale des tests.

Aucun test ne doit écrire dans D:/hub_telegram (pending.db réel) ni envoyer de
vraie notification Telegram. Cette fixture autouse stube les fonctions du hub à
travers `core.telegram_adapter` (les consommateurs font des imports tardifs
`from core.telegram_adapter import ...`). Tout test qui déclenche une relance
sans fixture `fake_tg` (ex. `test_run_relances_kill_switch_et_manuel`) reste
donc confiné en mémoire : plus de pollution du vrai pending.db, plus de notifs.
"""
import pytest

import core.telegram_adapter as ta


@pytest.fixture(autouse=True)
def _stub_telegram_hub(monkeypatch):
    store = {
        'requests': [],        # (outil, preview, callback_id, timeout_minutes)
        'status': {},          # callback_id -> 'ok' | 'no' | None
        'notifications': [],   # (outil, preview)
    }

    def _send_validation_request(outil, preview, callback_id, timeout_minutes=None):
        store['requests'].append((outil, preview, callback_id, timeout_minutes))
        store['status'].setdefault(callback_id, None)
        return 'pending'

    def _notify(outil, preview, action=None):
        store['notifications'].append((outil, preview))
        return None

    def _check_pending_db(callback_id, timeout_minutes=60):
        status = store['status'].get(callback_id)
        if status in ('ok', 'no'):
            store['status'][callback_id] = 'completed'
            return status
        return 'timeout'

    monkeypatch.setattr(ta, 'send_validation_request', _send_validation_request)
    monkeypatch.setattr(ta, 'notify', _notify)
    monkeypatch.setattr(ta, 'check_pending_db', _check_pending_db)
    return store