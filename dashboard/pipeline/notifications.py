# -*- coding: utf-8 -*-
"""
dashboard/pipeline/notifications.py
Gestion des notifications Telegram pour le pipeline.
"""
import logging
import threading
from datetime import datetime
from database.db_manager import get_conn

logger = logging.getLogger(__name__)

def _telegram_send(outil: str, preview: str, callback_id: str):
    """Envoie une demande de validation Telegram (non-bloquant)."""
    try:
        from core.telegram_adapter import send_validation_request
        send_validation_request(outil, preview, callback_id, timeout_minutes=300)
        logger.info(f"[PIPELINE-Notif] Telegram envoyé : {outil} (cb={callback_id})")
    except Exception as e:
        logger.error(f"[PIPELINE-Notif] Telegram send error: {e}")

def _telegram_wait(callback_id: str, timeout_seconds: int = 18000) -> str:
    """
    Attend la réponse Telegram. Bloquant jusqu'à timeout_seconds secondes.
    Retourne 'ok', 'no' ou 'timeout'.
    """
    try:
        from core.telegram_adapter import check_pending_db
        return check_pending_db(callback_id, timeout_minutes=timeout_seconds // 60)
    except Exception as e:
        logger.error(f"[PIPELINE-Notif] Telegram wait error: {e}")
        return "timeout"

def _notify_batch_sent(batch_key: str, scheduled_at: str, nb_emails: int):
    """Envoie une notification Telegram confirmant qu'un batch a été envoyé."""
    def _bg():
        try:
            from core.telegram_adapter import notify
            try:
                from datetime import datetime as _dt
                slot = _dt.fromisoformat(scheduled_at)
                slot_fr = slot.strftime("%A %d/%m à %Hh").capitalize()
            except Exception:
                slot_fr = scheduled_at

            msg = (
                f"*{nb_emails} emails envoyés — {slot_fr}*\n\n"
                f"Batch `{batch_key}` expédié par Resend ✅\n"
                f"Résultats disponibles dans le dashboard."
            )
            notify(f"Envoi {slot_fr}", msg)
        except Exception as e:
            logger.error(f"[PIPELINE-Notif] _notify_batch_sent: {e}")

    threading.Thread(target=_bg, daemon=True).start()

def _notify_and_watch_batch(batch_key: str, slot: datetime, nb: int, lead_ids: list):
    """
    Envoie une notification Telegram pour le batch (fire-and-forget).
    """
    def _bg():
        try:
            slot_fr = slot.strftime("%A %d/%m à %Hh").capitalize()
            preview_lines = []
            with get_conn() as conn:
                for lid in lead_ids[:6]:
                    row = conn.execute("""
                        SELECT lb.nom, la.email_objet FROM leads_bruts lb
                        JOIN leads_audites la ON la.lead_id = lb.id
                        WHERE lb.id = ?
                    """, (lid,)).fetchone()
                    if row:
                        nom = (row['nom'] or '')[:25]
                        obj = (row['email_objet'] or '')[:45]
                        preview_lines.append(f"• {nom} — {obj}")

            more = nb - len(preview_lines)
            msg = (
                f"*{nb} emails programmés — {slot_fr}*\n\n"
                + "\n".join(preview_lines)
                + (f"\n_...+{more} autres_" if more > 0 else "")
                + "\n\n✅ = envoi automatique à l'heure prévue"
                + "\n❌ = annuler ce batch (ou /annuler " + batch_key + ")"
            )

            cb = f"b_{batch_key}"
            _telegram_send(f"Batch {slot_fr}", msg, cb)

        except Exception as e:
            logger.error(f"[PIPELINE-Notif] _notify_and_watch_batch {batch_key}: {e}")

    threading.Thread(target=_bg, daemon=True).start()
