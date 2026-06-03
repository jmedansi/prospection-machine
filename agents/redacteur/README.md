# Agent — Rédacteur

## Rôle
Génère le contenu personnalisé de l'email (objet + corps HTML)
à partir des données d'audit via le copywriter et le builder email.

Détermine le profil (A, B, C, D) selon la situation du lead.

## Entrée
```python
redacteur_agent.run(lead_ids=[42, 43])
# ou pour un seul lead avec données de retour complètes :
redacteur_agent.run_one(42)
```

## Sortie (AgentResult)
```json
{
  "success": true,
  "agent": "redacteur",
  "data": { "success_count": 2, "total": 2, "errors": [] }
}
```

## Profils email
| Profil | Situation |
|--------|-----------|
| A | Pas de site web |
| B | Site lent / mauvais CMS / pas de contact |
| C | Peu d'avis / note faible |
| D | Pas de meta description |

## Échecs possibles
| error_type | Cause |
|------------|-------|
| `ValueError` | lead_ids vide |
| `MissingDataError` | Lead non audité (pas de données dans leads_audites) |

## Pipeline suivant
→ **ExpéditeurAgent** (envoyer l'email)
