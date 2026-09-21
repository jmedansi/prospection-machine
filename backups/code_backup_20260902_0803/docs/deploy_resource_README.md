# deploy_resource — Module de déploiement CTA pour GitHub Pages

Ce module permet de déployer des ressources CTA (pages web) depuis n'importe quel projet Python vers GitHub Pages.

---

## Fonctionnement

```
Projet A (Facebook Machine)
        │
        ▼ (appel API ou import)
deploy_resource.deploy_resource()
        │
        ▼ commit HTML → GitHub
   jmedansi/incidenx-audit
        │
        ▼ GitHub Pages
https://audit.incidenx.com/{slug}/
```

**URL publique** : `https://audit.incidenx.com/{slug}/`

---

## Installation dans Projet A

### Option 1 : Import Python direct

Copier `deploy_resource.py` à la racine du Projet A.

```python
from deploy_resource import deploy_resource

result = deploy_resource(
    slug="guide-facebook-monetisation-2025",
    title="Guide complet : Monétiser Facebook en 47 jours",
    content="""
# Introduction

Voici un guide complet pour monétiser votre page Facebook.

## Les bases

1. Créez du contenu de valeur
2. Engagez votre audience
3. Monetisez avec des produits

## Conclusion

Apply these steps consistently and you will see results.
""",
    theme="default"  # optionnel: default, blue, red, purple
)

if result["success"]:
    print(f"Page deployed: {result['url']}")
else:
    print(f"Error: {result['error']}")
```

### Option 2 : Appel HTTP (si Projet B tourne)

Le Projet B doit être démarré (`python dashboard/app.py`) et accessible.

```python
import requests

def deploy_resource_remote(slug, title, content, theme="default"):
    response = requests.post(
        "http://localhost:5001/api/deploy-resource",  # ou URL distante
        json={
            "slug": slug,
            "title": title,
            "content": content,
            "theme": theme
        }
    )
    return response.json()
```

---

## Paramètres

| Paramètre | Type | Obligatoire | Description |
|----------|------|-----------|-------------|
| `slug` | string | ✅ | Identifiant unique (ex: `guide-facebook-2025`) |
| `title` | string | ✅ | Titre de la page |
| `content` | string | ✅ | Contenu Markdown ou HTML |
| `theme` | string | ❌ | Thème visuel : `default`, `blue`, `red`, `purple` |

---

## Réponse

```python
# Succès
{"success": True, "url": "https://audit.incidenx.com/guide-facebook-2025/", "slug": "guide-facebook-2025"}

# Erreur
{"success": False, "error": "Missing required fields"}
```

---

## Configuration requise

Le module utilise ces variables d'environnement :

- `GITHUB_TOKEN` — Token d'accès GitHub (repo content)
- `AUDIT_DOMAIN` — Domaine GitHub Pages (défaut: `audit.incidenx.com`)

---

## Intégration rapide dans Projet A

```python
# Dans facebook_machine.py ou votre script principal

import os
import sys

# Ajouter le chemin vers Projet B
sys.path.append("D:/prospection-machine")

from deploy_resource import deploy_resource

def publish_cta(slug, title, content):
    """Publie une资源 CTA et retourne l'URL."""
    result = deploy_resource(slug=slug, title=title, content=content, theme="default")
    if result.get("success"):
        return result["url"]
    else:
        raise Exception(result.get("error"))

# Exemple d'utilisation
if __name__ == "__main__":
    url = publish_cta(
        slug="fb-monetization-guide",
        title="Monétisez votre page Facebook",
        content="# Guide complet\n\nTout ce que..."
    )
    print(f"Published: {url}")
```