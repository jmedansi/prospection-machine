---
module: scraper/sniper/jobs_scraper.py
---

# scraper/sniper/jobs_scraper.py — Source 3 : Offres d'emploi France Travail

## Rôle
Détecte des entreprises qui recrutent sur des postes tech/digital via l'API
France Travail (ex Pôle Emploi). Une offre pour "Développeur WordPress" ou
"Responsable e-commerce" prouve que l'entreprise a un budget digital actif.

## Signal de budget
Une offre d'emploi sur un poste tech = l'entreprise paie déjà pour cette
infrastructure. Elle peut payer pour l'optimiser.

## Flux
```
JobsScraper.run(keywords, max_offers_per_kw, days_back, max_leads)
  → _get_ft_token()       ← OAuth2 France Travail (cache 25 min)
  → _fetch_offers()       ← offres des N derniers jours par mot-clé
  → _extract_domain()     ← site web depuis entreprise.url ou urlPostulation
  → déduplication         ← 1 offre par domaine
  → Wappalyzer            ← CMS auto-géré ? (rejet rapide)
  → PageSpeed             ← si site non auto-géré
  → score_lead()          ← tag_urgence + niveau_urgence
  → INSERT leads_bruts source='jobs'
```

## Configuration .env
```
FT_CLIENT_ID=...        ← depuis https://francetravail.io (inscription gratuite)
FT_CLIENT_SECRET=...
```
Si les variables sont absentes, le module se désactive silencieusement.

## Mots-clés par défaut (`DEFAULT_KEYWORDS`)
- `développeur WordPress`, `développeur PrestaShop`, `développeur e-commerce`
- `responsable e-commerce`, `chef de projet digital`, `développeur Shopify`
- `intégrateur web`, `développeur full stack`, `traffic manager`
- `responsable acquisition`, `growth hacker`, `développeur Magento`

## Extraction du domaine
Ordre de priorité :
1. `entreprise.url` (rarement renseigné par l'API)
2. `contact.urlPostulation` → extraction du domaine racine
3. Aucun domaine → offre ignorée

## Routes API
- `POST /api/sniper/jobs-scan` — scan manuel
  ```json
  {"keywords": ["développeur WordPress"], "max_offers_per_kw": 50,
   "days_back": 7, "max_leads": 50}
  ```
- `GET /api/sniper/jobs-status` — état en temps réel

## Règles
- `approuve` toujours à `0` — validation manuelle obligatoire
- Déduplication sur `site_web` : un même domaine ne peut avoir qu'un lead actif `source='jobs'`
- `days_back` par défaut à 7 — offres récentes seulement (entreprises en phase de croissance)
- Ne pas augmenter `parallel` au-delà de 5 (quota API France Travail)
