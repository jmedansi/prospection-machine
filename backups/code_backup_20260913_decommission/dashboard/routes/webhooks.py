# -*- coding: utf-8 -*-
"""
dashboard/routes/webhooks.py
Réception des webhooks (Resend, Brevo, etc.) pour le suivi des interactions.
"""
from flask import Blueprint, request, jsonify
from datetime import datetime
from database.repos.emails_repo import emails_repo
import logging

logger = logging.getLogger(__name__)
webhooks_bp = Blueprint('webhooks', __name__, url_prefix='/api/webhooks')

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

    return jsonify({"status": "success"}), 200

@webhooks_bp.route('/test', methods=['GET', 'POST'])
def test_webhook():
    return jsonify({"status": "ok", "message": "Webhook endpoint is active"}), 200
