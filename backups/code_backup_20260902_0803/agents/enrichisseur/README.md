# Agent — Enrichisseur

## Rôle
Enrichit un lead avec des données manquantes : email CEO (via scraping LinkedIn/web),
validation SMTP de l'email existant.

## Entrée
```python
enrichisseur_agent.run(lead_id=42)
```

## Sortie (AgentResult)
```json
{
  "success": true,
  "agent": "enrichisseur",
  "data": {
    "lead_id": 42,
    "enriched_fields": { "email": "contact@entreprise.fr", "email_valide": "Valide" }
  }
}
```

## Échecs possibles
| error_type | Cause |
|------------|-------|
| `NotFoundError` | lead_id inexistant en base |

## Pipeline suivant
→ **AuditeurAgent**
