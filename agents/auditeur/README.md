# Agent — Auditeur

## Rôle
Lance l'analyse technique des sites web (PageSpeed, SEO, GMB, LCP)
via `auditeur/main.py` en sous-processus asynchrone.
Stocke les résultats dans `leads_audites`.

## Entrée
```python
# Par IDs
auditeur_agent.run(lead_ids=[42, 43, 44])
# Par noms
auditeur_agent.run(lead_names=["Mon Client", "Autre Client"])
# Batch automatique
auditeur_agent.run(limit=20)
```

## Sortie (AgentResult)
```json
{
  "success": true,
  "agent": "auditeur",
  "data": { "message": "Audit lancé", "total": 3 },
  "duration_ms": 12
}
```
⚠️ L'agent retourne immédiatement (asynchrone). Utiliser `auditeur_agent.status()` pour suivre la progression.

## Statut en temps réel
```python
auditeur_agent.status()
# → { "running": true, "current": 2, "total": 3, "failed": 0, "logs": [...] }
```

## Échecs possibles
| error_type | Cause |
|------------|-------|
| `ConflictError` | Un audit est déjà en cours |
| `ValueError` | Aucun paramètre fourni |

## Pipeline suivant
→ **ÉditeurAgent** (générer le rapport HTML)
