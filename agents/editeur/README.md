# Agent — Éditeur

## Rôle
Génère le rapport HTML d'audit personnalisé pour un lead
et le sauvegarde localement dans `reporter/reports/{slug}/`.

## Entrée
```python
editeur_agent.run(lead_id=42)
```

## Sortie (AgentResult)
```json
{
  "success": true,
  "agent": "editeur",
  "data": {
    "lead_id": 42,
    "slug": "mon-client-paris",
    "local_path": "reporter/reports/mon-client-paris/",
    "local_url": "http://127.0.0.1:5001/previews/mon-client-paris/",
    "lien_rapport": "local://mon-client-paris/"
  }
}
```

## Prévisualisation locale
Le rapport est accessible via `GET /previews/{slug}/` sur le serveur Flask local.

## Échecs possibles
| error_type | Cause |
|------------|-------|
| `ImportError` | Module reporter.main introuvable |
| `ReportError` | run_report_for_lead a retourné None |

## Pipeline suivant
→ **PublieurAgent** (publier sur GitHub Pages)
