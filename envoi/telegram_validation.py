# -*- coding: utf-8 -*-
"""
envoi/telegram_validation.py — validation Telegram d'un envoi v2.

Un objectif avec `validation_telegram=1` exige un ✅ Telegram avant envoi.
Le pattern reprend le legacy (pending.db + send_validation_request) :
    - `request(...)`     : envoie la demande de validation (outil + callback_id)
    - `get_status(...)`  : 'ok' | 'ko' | None (non répondu) | 'completed'
    - `mark_completed()` : consomme la réponse après traitement (idempotence)
    - `callback_id()`    : `v2_approve_{prospect_id}`
"""
import os
import sqlite3
import logging

from core.config import HUB_TELEGRAM

logger = logging.getLogger(__name__)


def pending_db() -> str:
    path = os.path.join(HUB_TELEGRAM, 'pending.db')
    if not os.path.exists(path):
        return None
    return path


def callback_id(prospect_id: int) -> str:
    return f"v2_approve_{int(prospect_id)}"


def has_requested(callback_id_value: str) -> bool:
    db = pending_db()
    if not db:
        return False
    try:
        conn = sqlite3.connect(db)
        row = conn.execute(
            "SELECT 1 FROM pending WHERE callback_id = ?", (callback_id_value,)
        ).fetchone()
        conn.close()
        return row is not None
    except Exception as e:
        logger.error("[tg_validation] has_requested %s: %s", callback_id_value, e)
        return False


def get_status(callback_id_value: str) -> str | None:
    db = pending_db()
    if not db:
        return None
    try:
        conn = sqlite3.connect(db)
        row = conn.execute(
            "SELECT status FROM pending WHERE callback_id = ? ORDER BY id DESC LIMIT 1",
            (callback_id_value,),
        ).fetchone()
        conn.close()
        return row[0] if row else None
    except Exception as e:
        logger.error("[tg_validation] get_status %s: %s", callback_id_value, e)
        return None


def mark_completed(callback_id_value: str) -> bool:
    db = pending_db()
    if not db:
        return False
    try:
        conn = sqlite3.connect(db)
        conn.execute(
            "UPDATE pending SET status='completed' WHERE callback_id = ?", (callback_id_value,)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error("[tg_validation] mark_completed %s: %s", callback_id_value, e)
        return False


def build_preview(objectif_nom, prospect, objet, corps, step_label='Envoi initial'):
    """Aperçu Telegram affiché avec les boutons ✅/❌."""
    from envoi.smtp_sender import _strip_html
    nom = prospect.get('entreprise') or prospect.get('nom') or '?'
    to = prospect.get('email') or '?'
    text = f"*{step_label}*\nObjectif : {objectif_nom}\nSociété : {nom}\nContact : {to}\n\nObjet : {objet}\n\n{'─'*30}\n{_strip_html(corps)[:360]}..."
    return text


def request(objectif, prospect, objet, corps, step_label='Envoi initial') -> dict:
    """Envoie la demande de validation Telegram. Retourne {'success', 'callback_id'}."""
    cb = callback_id(prospect['id'])
    try:
        from core.telegram_adapter import send_validation_request
        preview = build_preview(objectif.get('nom', ''), prospect, objet, corps, step_label)
        # timeout 48h (comme le legacy relances)
        send_validation_request(outil=f"v2_{objectif['id']}_{prospect['id']}", preview=preview,
                                callback_id=cb, timeout_minutes=2880)
        return {'success': True, 'callback_id': cb}
    except Exception as e:
        logger.error("[tg_validation] request %s: %s", cb, e)
        return {'success': False, 'callback_id': cb, 'error': str(e)}


def reset_for_prospect(prospect_id: int):
    """Retire les réponses pendantes (utile en test)."""
    db = pending_db()
    if not db:
        return
    try:
        conn = sqlite3.connect(db)
        conn.execute("DELETE FROM pending WHERE callback_id = ?", (callback_id(prospect_id),))
        conn.commit()
        conn.close()
    except Exception:
        pass


def notify_answer(prospect: dict, subject: str = '', snippet: str = '') -> bool:
    """Notification Telegram dès qu'un prospect répond (réponse reçue).

    Jamais bloquant : no-op si le hub est absent, sinon envoi d'un texte simple
    (sans boutons d'action). Retourne True si le message a (au mieux) été transmis.
    """
    try:
        from core.telegram_adapter import notify
    except Exception:
        return False
    ident = prospect.get('entreprise') or prospect.get('nom') or prospect.get('prenom') or '?'
    preview = (f"{ident} — {prospect.get('email') or ''}\n"
               f"Objet : {subject or '(sans objet)'}\n"
               f"{snippet or ''}").strip()
    try:
        notify('📬 Réponse reçue', preview)
        return True
    except Exception as e:
        logger.error("[tg_validation] notify_answer %s: %s", prospect.get('id'), e)
        return False