---
module: scraper/sniper/tech_scraper.py
---

# scraper/sniper/tech_scraper.py — Source 2 : Tech Stack B2B

## Rôle
Trouve des entreprises B2B ayant un CMS coûteux (WordPress, PrestaShop, Shopify…)
via l'API Entreprises du gouvernement, filtre par taille (≥ 10 salariés),
et injecte les leads qualifiés dans `leads_bruts` avec `source='tech'`.

Signal de budget : une PME qui paie pour un WooCommerce ou un PrestaShop
a déjà investi dans sa présence web — c'est la même preuve de budget que Google Ads.

## Flux
```
TechScraper.run(naf_codes, max_companies, max_leads)
  → API recherche-entreprises.api.gouv.fr (par code NAF + effectif ≥ 10)
  → filtre : site_internet présent
  → Wappalyzer  ← CMS détecté ?
  → si CMS ∈ HIGH_VALUE_CMS : PageSpeed mobile
  → score_lead(pagespeed, wap, source='tech')
  → INSERT leads_bruts source='tech'
```

## Différence avec Source 1 (Ads)
| Source 1 Ads | Source 2 Tech |
|---|---|
| Entreprises qui achètent des pubs Google | Entreprises avec CMS à budget signal |
| Signal : enchères AdWords | Signal : WordPress/Shopify/PrestaShop détecté |
| Scraper : Google Ads pages | Scraper : API Entreprises gov.fr |

## API utilisée
`https://recherche-entreprises.api.gouv.fr/search` — **gratuite, sans clé**.
Paramètres : `activite_principale` (NAF), `per_page=25`, `page`.

## Filtres appliqués
1. **NAF** : codes B2B digital (6201Z, 7311Z, 7022Z…) — liste dans `DEFAULT_NAF`
2. **Effectif** : `tranche_effectif_salarie ≥ "11"` (10+ salariés)
3. **Site web** : `siege.site_internet` obligatoire
4. **CMS** : rejet uniquement si CMS auto-géré (Wix, Squarespace, Weebly, Jimdo…)
   — un site full-code (`cms=None`) ou tout autre CMS est **accepté** : c'est un prestataire web impliqué
5. **Score** : `score_lead()` doit retourner un tag (sinon rejeté)

## Logique de filtre CMS
On ne cherche PAS à détecter un CMS spécifique. On rejette uniquement les outils
"no-code" que le client gère lui-même sans prestataire. Tout le reste (WordPress,
PrestaShop, Shopify, Next.js, full custom…) signale un budget web réel.

## Déduplication
SIREN stocké dans `donnees_audit` JSON — un même SIREN ne peut pas avoir deux leads
actifs avec `source='tech'`.

## Configuration
Aucune variable `.env` requise pour ce module.
Optionnel : `PAGESPEED_API_KEY` (accélère les requêtes PageSpeed).

## Scheduler
Non planifié en automatique — lancé manuellement depuis le dashboard.
Route : `POST /api/sniper/tech-scan`

## Règles
- Ne pas augmenter `parallel` au-dessus de 5 (Wappalyzer + PageSpeed consomment du CPU)
- `max_leads` par défaut à 50 par run — ne pas saturer la DB
- `approuve` toujours à `0` à la création (validation manuelle obligatoire)
