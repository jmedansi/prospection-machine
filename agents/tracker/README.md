# Agent — Tracker

## Rôle
Traite les événements de tracking email (webhooks Resend)
et met à jour les champs de suivi dans `emails_envoyes` + `email_events`.

## Entrée
```python
# Depuis un webhook
tracker_agent.handle_webhook(
    event_type="email.opened",
    message_id="msg_abc123",
    timestamp="2026-04-10T10:00:00Z",
    meta={}
)
# Polling manuel (fallback si webhook non reçu)
tracker_agent.poll_status(message_id="msg_abc123")
```

## Événements supportés
| event_type | Action DB |
|------------|-----------|
| `email.sent` | statut_envoi = "envoye" |
| `email.delivered` | statut_envoi = "delivre" |
| `email.opened` | ouvert = 1, date_ouverture |
| `email.clicked` | clique = 1, date_clic |
| `email.bounced` | bounce = 1 |
| `email.complained` | spam = 1 |

## Sortie (AgentResult)
```json
{
  "success": true,
  "agent": "tracker",
  "data": { "message_id": "msg_abc123", "event_type": "email.opened", "updated": true }
}
```

## Échecs possibles
| error_type | Cause |
|------------|-------|
| `ValueError` | message_id ou event_type manquant |
| `ConfigError` | RESEND_API_KEY non configurée (poll uniquement) |
