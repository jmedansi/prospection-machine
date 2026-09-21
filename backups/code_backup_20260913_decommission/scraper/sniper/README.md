# scraper/sniper/ — Couche acquisition du pipeline Sniper

**Lire ce fichier avant toute modification.**

---

## Rôle

Extraire les domaines/entreprises cibles depuis 3 sources actives (Ads, Tech, Jobs).
La source BODACC est dans `sniper/bodacc_scanner.py` (scraping officiel API, pas Playwright).

Ce dossier appartient à la **couche acquisition** — aucun envoi d'email ici.
La couche email est dans `sniper/` (séparée intentionnellement).

---

## Sources

| Fichier | Source | Méthode | Statut |
|---------|--------|---------|--------|
| `ads_extractor.py` | Source 1 — Google/Bing Ads | Patchright (anti-bot) | ✅ |
| `tech_scraper.py` | Source 2 — API Entreprises | API gouv.fr + Wappalyzer Node.js | ✅ |
| `jobs_scraper.py` | Source 3 — France Travail | OAuth2 client_credentials | ✅ ⚠️ activer app |
| `pipeline.py` | Orchestrateur Ads (Phases 1→4) | thread background | ✅ |
| `scoring.py` | Scoring leads | tag_urgence + niveau | ✅ |
| `wappalyzer_runner.py` | Wappalyzer | Node.js subprocess | ✅ |

---

## Source 1 — Ads (ads_extractor.py)

**Flux :** mots-clés → Google.fr (data-text-ad) → nettoyage URL → domaines uniques

**Utilisé par :**
- `pipeline.py` Phase 1
- Route `/api/sniper/launch` → `services/sniper_runner.launch_sniper()`
- Dashboard : bouton "Recherche Ads" → `showSniperLaunchModal()`

**Paramètres :**
- `keywords` : liste de requêtes transactionnelles (ex: "logiciel ERP PME Paris")
- `country` : fr / ch / be / lu
- `max_per_kw` : max annonceurs par mot-clé (défaut 8)

**Blacklist domaines :** wix.com, facebook.com, amazon.fr, ebay.fr, etc.

---

## Source 2 — Tech (tech_scraper.py)

**Flux :** API Entreprises (q=secteur, NAF, effectif≥10) → Wappalyzer → rejet si CMS auto-géré

**CMS auto-gérés rejetés (blacklist) :**
Wix, Squarespace, Weebly, Jimdo, Webflow, Blogger, Tumblr, GoDaddy Website Builder, Strikingly, Carrd, Notion, Site123

**Tout le reste accepté** : WordPress, full-code, custom, Shopify, PrestaShop, etc.

Voir `TECH_SCRAPER_README.md` pour le détail.

---

## Source 3 — Jobs (jobs_scraper.py)

**Flux :** France Travail OAuth2 → offres RH digitales → domaine entreprise → leads

**Auth :** client_credentials, token TTL 25min, renewal auto
**Credentials :** FT_CLIENT_ID + FT_CLIENT_SECRET dans .env

⚠️ **Action requise** : activer l'app sur https://francetravail.io → "Mes applications"
Actuellement : `invalid_client` (app pas encore activée)

Voir `JOBS_SCRAPER_README.md` pour le détail.

---

## Pipeline Ads complet (pipeline.py)

```
Phase 1    ads_extractor     keywords → [domaine, mot_cle, pays]
Phase 1.5  pre_filter        top 30 par heat_score (TTFB + GTM)
           contact_finder    email contact@ + tél
           ceo_finder        API gouv.fr → Groq → Ollama
           email_permutations + smtp_validator
Phase 2    PageSpeed + Wappalyzer (parallèle, 3 threads)
Phase 3    scoring.score_lead → tag_urgence + niveau ou rejet
Phase 4    insert leads_bruts (source='ads')
```

**État partagé :** `_state` dict pollé par `/api/sniper/status`
**Campagne créée** en début de run, liée à chaque lead via campaign_id

---

## Règles

1. Ne jamais importer depuis `copywriter/` ou `envoi/`
2. Pas de logique email ici — uniquement extraction et scoring
3. Pour ajouter une source : créer `source_X.py` + documenter ici + ajouter route dans `dashboard/routes/campaigns.py`
4. Les leads insérés ont toujours `statut='en_attente'` et `approuve=0`
