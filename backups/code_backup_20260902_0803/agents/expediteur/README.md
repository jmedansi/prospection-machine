# Agent — Expéditeur

## Rôle
Envoie les emails approuvés via Resend, enregistre chaque envoi
dans `emails_envoyes` et planifie les séquences de relance.

## Entrée
```python
# Envoyer tous les emails approuvés
expediteur_agent.run()
# Envoyer des leads spécifiques
expediteur_agent.run(lead_ids=[42, 43])
# Envoyer un email de test
expediteur_agent.send_test(lead_id=42, to_email="moi@email.com")
```

## Sortie (AgentResult)
```json
{
  "success": true,
  "agent": "expediteur",
  "data": { "message": "Envoi de 3 emails lancé", "total": 3 }
}
```

## Statut en temps réel
```python
expediteur_agent.status()
# → { "running": true, "current": 1, "total": 3, "success": 1, "failed": 0 }
```

## Échecs possibles
| error_type | Cause |
|------------|-------|
| `ConflictError` | Un envoi est déjà en cours |
| `EmptyQueueError` | Aucun email approuvé à envoyer |
| `SendError` | Erreur API Resend |

## Pipeline suivant
→ **TrackerAgent** (suivre les ouvertures via webhooks)
