# Agent — Scraper

## Rôle
Lance un scraping Google Maps pour un mot-clé + ville donné.
Crée une campagne en base et démarre `scraper/main.py` en sous-processus.

## Entrée
```python
scraper_agent.run(
    keyword="plombier",
    city="Paris",
    sector="plomberie",   # optionnel
    limit=50,
    min_emails=10,
    campaign_name=""      # auto si vide
)
```

## Sortie (AgentResult)
```json
{
  "success": true,
  "agent": "scraper",
  "data": { "campaign_id": 12, "message": "Scraping lancé pour 'plombier' à 'Paris'" },
  "error": null,
  "duration_ms": 45
}
```

## Échecs possibles
| error_type | Cause |
|------------|-------|
| `ValueError` | keyword ou city manquant |
| `DBError` | Impossible de créer la campagne en base |
| `FileNotFoundError` | Exécutable Python introuvable |

## Pipeline suivant
→ **EnrichisseurAgent** (valider emails)  
→ **AuditeurAgent** (analyser les sites)
