# -*- coding: utf-8 -*-
"""
dashboard/routes/webhooks.py
Réception des webhooks (Resend, Brevo, etc.) pour le suivi des interactions.
"""
from flask import Blueprint, request, jsonify, redirect
from datetime import datetime
from database.repos.emails_repo import emails_repo
from database import emails as emails_db
from database import prospects as prospects_repo
from urllib.parse import urlparse, unquote
import logging

logger = logging.getLogger(__name__)
webhooks_bp = Blueprint('webhooks', __name__, url_prefix='/api/webhooks')

# Événements qui rendent l'adresse inutilisable → suppression_list (spec §8)
_SUPPRESS_ON = {'email.bounced': 'bounce_dur', 'email.complained': 'plainte'}

# ── Tracking maison SMTP : pixel d'ouverture 1x1 (voir envoi/track_links.py) ─────
_PIXEL_GIF = (
    b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00'
    b'\xff\xff\xff\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00'
    b'\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b'
)


@webhooks_bp.route('/track/pixel/<path:message_id>', methods=['GET'])
def track_pixel(message_id):
    """Pixel d'ouverture : marque l'email comme ouvert puis renvoie un GIF 1x1."""
    try:
        mid = unquote(message_id)
        if mid:
            emails_db.update_email_tracking(mid, {
                'ouvert': 1,
                'date_ouverture': datetime.now().isoformat(),
            })
            from database.db_manager import get_conn
            with get_conn() as conn:
                conn.execute(
                    "UPDATE emails_envoyes SET nb_ouvertures = nb_ouvertures + 1 "
                    "WHERE message_id_resend = ? OR message_id_brevo = ?",
                    (mid, mid))
                conn.commit()
    except Exception as e:
        logger.error(f"[TRACK] pixel {message_id}: {e}")
    return _PIXEL_GIF, 200, {'Content-Type': 'image/gif', 'Cache-Control': 'no-store'}


@webhooks_bp.route('/track/click/<path:message_id>', methods=['GET'])
def track_click(message_id):
    """Wrapper de clic : enregistre le clic puis redirige vers l'URL d'origine."""
    msg = request.args.get('u') or ''
    parsed = urlparse(msg)
    if not parsed.scheme or parsed.scheme not in ('http', 'https'):
        return jsonify({"status": "error", "reason": "url invalide"}), 400
    try:
        mid = unquote(message_id)
        if mid:
            emails_db.update_email_tracking(mid, {
                'clique': 1,
                'date_clic': datetime.now().isoformat(),
            })
            from database.db_manager import get_conn
            with get_conn() as conn:
                conn.execute(
                    "UPDATE emails_envoyes SET nb_clics = nb_clics + 1, "
                    "date_dernier_clic = ? WHERE message_id_resend = ? OR message_id_brevo = ?",
                    (datetime.now().isoformat(), mid, mid))
                conn.commit()
    except Exception as e:
        logger.error(f"[TRACK] click {message_id}: {e}")
    return redirect(msg, code=302)

def _suppress_recipient(event_data: dict, raison: str, message_id: str) -> str:
    """Noircit le destinataire dans suppression_list (spec §8) + file de bounces.

    Le payload Resend porte `to`, mais il est parfois vide (événements
    partiels) : on retombe sur l'adresse journalisée dans emails_envoyes.
    Sans cet ajout, un bounce ne bloquait RIEN — `ne_plus_contacter` restait à 0
    et la séquence re-ciblait l'adresse au tour suivant.
    """
    to = event_data.get('to') or []
    if isinstance(to, str):
        to = [to]
    addr = (to[0] if to else '') or emails_repo.get_address(message_id) or ''
    if '@' not in (addr or ''):
        logger.warning(f"[WEBHOOK] {raison} : adresse introuvable pour {message_id}")
        return ''
    if prospects_repo.add_to_suppression_list(addr, raison):
        logger.info(f"[WEBHOOK] {raison} : {addr.strip().lower()} → suppression_list")
    # File de traitement + notif Telegram ✅/❌ (→ 🗑 Corbeille / ignoré)
    try:
        from core.bounce_handler import record_bounce
        record_bounce(addr, raison=raison, motif=event_data.get('reason'),
                      email_record_id=emails_repo.get_record_id(message_id))
    except Exception as e:
        logger.error(f"[WEBHOOK] record_bounce {addr}: {e}")
    return addr


@webhooks_bp.route('/resend', methods=['POST'])
def resend_webhook():
    """
    Webhook Resend pour email.opened, email.clicked, email.bounced, email.complained.
    """
    data = request.json
    if not data:
        return jsonify({"status": "ignored", "reason": "no data"}), 400

    # Resend envoie parfois une liste d'événements ou un objet unique
    if isinstance(data, list):
        events = data
    else:
        events = [data]

    for event in events:
        event_type = event.get("type")
        event_data = event.get("data", {})
        message_id = event_data.get("email_id")
        
        if not message_id:
            continue

        timestamp = event.get("created_at") or datetime.now().isoformat()
        
        logger.info(f"[WEBHOOK] Resend {event_type} pour {message_id}")

        # 1. Logger l'événement complet dans email_events
        success_log = emails_repo.log_event(message_id, event_type, timestamp, event_data)
        if not success_log:
            logger.warning(f"[WEBHOOK] Échec log_event pour {message_id}")

        # 2. Mettre à jour l'état de l'email dans emails_envoyes
        fields = {}
        if event_type == "email.opened":
            fields = {
                "ouvert": 1,
                "date_ouverture": timestamp,
            }
        elif event_type == "email.clicked":
            fields = {
                "clique": 1,
                "date_clic": timestamp,
            }
        elif event_type == "email.bounced":
            fields = {
                "bounce": 1,
                "statut_envoi": "bounced"
            }
        elif event_type == "email.complained": # Spam
            fields = {
                "spam": 1
            }
        elif event_type == "email.delivered":
            fields = {
                "statut_envoi": "delivered"
            }

        if fields:
            emails_repo.update_tracking(message_id, fields)

        # 3. Bounce dur / plainte → liste noire globale (bloque campagnes futures)
        if event_type in _SUPPRESS_ON:
            _suppress_recipient(event_data, _SUPPRESS_ON[event_type], message_id)

    return jsonify({"status": "success"}), 200

@webhooks_bp.route('/test', methods=['GET', 'POST'])
def test_webhook():
    return jsonify({"status": "ok", "message": "Webhook endpoint is active"}), 200
