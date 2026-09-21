# -*- coding: utf-8 -*-
"""
agents/tracker/agent.py — TrackerAgent

Responsabilité unique : traiter les événements de tracking email
(ouverture, clic, réponse, bounce) depuis les webhooks Resend
et mettre à jour la base de données.

Entrée  : event_type, message_id, timestamp, meta
Sortie  : AgentResult { message_id, event_type, updated }
"""
from __future__ import annotations
from core.result import BaseAgent, AgentResult, timed
from database.repos import emails_repo

# Mapping événements Resend → champs DB
EVENT_MAP = {
    "email.sent":      {"statut_envoi": "envoye"},
    "email.delivered": {"statut_envoi": "delivre"},
    "email.opened":    {"ouvert": 1, "statut_envoi": "ouvert"},
    "email.clicked":   {"clique": 1, "statut_envoi": "clique"},
    "email.bounced":   {"bounce": 1, "statut_envoi": "bounce"},
    "email.complained":{"spam": 1,   "statut_envoi": "spam"},
}


class TrackerAgent(BaseAgent):
    name = "tracker"

    @timed("tracker")
    def handle_webhook(self, event_type: str, message_id: str,
                       timestamp: str = "", meta: dict | None = None) -> AgentResult:
        """
        Traite un événement webhook entrant.

        Args:
            event_type:  Type d'événement Resend (ex: "email.opened")
            message_id:  ID du message Resend
            timestamp:   Timestamp ISO de l'événement
            meta:        Données supplémentaires du webhook

        Returns:
            AgentResult.data = { "message_id", "event_type", "updated": bool }
        """
        if not message_id:
            return self.fail("message_id requis")
        if not event_type:
            return self.fail("event_type requis")

        meta = meta or {}

        # Log l'événement dans email_events
        emails_repo.log_event(message_id, event_type, timestamp, meta)

        # Mettre à jour les champs de tracking
        fields = EVENT_MAP.get(event_type, {})
        updated = False
        if fields:
            if timestamp and "date_ouverture" not in fields and event_type == "email.opened":
                fields["date_ouverture"] = timestamp
            if timestamp and event_type == "email.clicked":
                fields["date_clic"] = timestamp
            updated = emails_repo.update_tracking(message_id, fields)

        self.logger.info(f"Webhook {event_type} pour {message_id} — updated={updated}")
        return self.ok({
            "message_id": message_id,
            "event_type": event_type,
            "updated":    updated,
        })

    @timed("tracker")
    def poll_status(self, message_id: str) -> AgentResult:
        """
        Interroge l'API Resend pour connaître le statut d'un email spécifique.
        Fallback quand le webhook n'a pas été reçu.

        Returns:
            AgentResult.data = { "status": str, "updated": bool }
        """
        try:
            import os, requests
            key = os.getenv("RESEND_API_KEY", "")
            if not key:
                return self.fail("RESEND_API_KEY non configurée", error_type="ConfigError")

            resp = requests.get(
                f"https://api.resend.com/emails/{message_id}",
                headers={"Authorization": f"Bearer {key}"},
                timeout=10,
            )
            resp.raise_for_status()
            data    = resp.json()
            status  = data.get("last_event", "unknown")
            updated = emails_repo.update_tracking(message_id, {"statut_envoi": status})
            return self.ok({"message_id": message_id, "status": status, "updated": updated})
        except Exception as e:
            return self.fail(str(e), error_type=type(e).__name__)


tracker_agent = TrackerAgent()
