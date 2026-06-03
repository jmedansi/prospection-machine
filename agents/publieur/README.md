# Agent — Publieur

## Rôle
Publie un ou plusieurs rapports locaux sur GitHub Pages
et met à jour `lien_rapport` en base de données.

## Entrée
```python
publieur_agent.run(slugs=["mon-client-paris", "autre-client"])
```

## Sortie (AgentResult)
```json
{
  "success": true,
  "agent": "publieur",
  "data": {
    "published": [{ "slug": "mon-client-paris", "url": "https://audit.incidenx.com/mon-client-paris/" }],
    "failed": []
  }
}
```

## Lister les rapports locaux
```python
publieur_agent.list_local()
# → [{ "slug": "...", "local": true, "local_url": "http://..." }]
```

## Échecs possibles
| error_type | Cause |
|------------|-------|
| `ImportError` | Module report_publishing introuvable |
| `ValueError` | Dossier ou index.html manquant |

## Pipeline suivant
→ **RédacteurAgent** (générer l'email)
