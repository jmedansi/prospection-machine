# sniper/enrichment/ — Module d'enrichissement dirigeant

**Lire ce fichier avant toute modification.**

---

## Rôle

Ce module transforme un domaine annonceur brut en lead qualifié avec :
- Score de chaleur (pre-filter rapide)
- Email de contact générique (contact@, info@...)
- Numéro de téléphone
- Nom du décideur (CEO/fondateur)
- Email personnel validé du décideur

## Position dans le pipeline

```
Phase 1  : extraction annonceurs        (scraper/sniper/ads_extractor.py)
Phase 1.5: PRE-FILTER (ce module)       ← ici, ~3s/site, rejette 80% des leads
Phase 2  : PageSpeed + Wappalyzer       (scraper/sniper/pipeline.py)
Phase 3  : scoring                      (scraper/sniper/scoring.py)
Phase 4  : DB insert + email génération (sniper/email_generator.py)
```

## Modules

| Fichier | Rôle | Dépendances |
|---|---|---|
| `pre_filter.py` | TTFB + GTM + score chaleur | requests |
| `contact_finder.py` | email/tel depuis le site | requests, bs4 |
| `ceo_finder.py` | Google dork → prénom/nom décideur | SerpApi (optionnel) ou Ollama |
| `email_permutations.py` | génère les 5 variantes email | - |
| `smtp_validator.py` | catch-all test + RCPT TO validation | socket, dns.resolver |

## Flux d'enrichissement

```
domaine.com
    │
    ├── pre_filter()      → heat_score, has_gtm, ttfb_ms
    │   └── si score < 4 → rejeté (pas d'audit complet)
    │
    ├── contact_finder()  → email_contact, telephone
    │
    ├── ceo_finder()      → prenom, nom
    │   ├── primaire  : Google dork site:linkedin.com + SerpApi
    │   └── fallback  : Ollama sur mentions légales (enrichisseur/ceo_finder.py)
    │
    ├── email_permutations() → [jean.dupont@, j.dupont@, ...]
    │
    └── smtp_validator()
            ├── DNS MX lookup
            ├── catch-all test (adresse absurde)
            ├── si strict  → RCPT TO sur chaque permutation → email_valide
            └── si catch-all → email_valide = email_contact, copywriting = 'transfert'
```

## Variables produites

Ajoutées au dict lead avant DB insert :

| Variable | Type | Description |
|---|---|---|
| `heat_score` | int 0-12 | Score de chaleur pré-filtrage |
| `has_gtm` | bool | Google Tag Manager présent |
| `ttfb_ms` | int | Time To First Byte en ms |
| `email_contact` | str | Email générique trouvé sur le site |
| `telephone` | str | Téléphone trouvé sur le site |
| `ceo_prenom` | str | Prénom du décideur |
| `ceo_nom` | str | Nom du décideur |
| `email_valide` | str | Email validé par SMTP |
| `email_source` | str | 'smtp_verified' / 'catch_all_contact' / 'site_only' |
| `copywriting_mode` | str | 'direct' (CEO trouvé) / 'transfert' (catch-all) |

## Configuration .env requise

```
SERPAPI_KEY=...         # Optionnel — fallback Ollama si absent
IMAP_HOST=mail.incidenx.com
IMAP_PORT=993
IMAP_USER=jmedansi@incidenx.com
IMAP_PASSWORD=...
```

## Règles

1. Ne jamais importer depuis `copywriter/` ou `auditeur/` (modules Maps)
2. `smtp_validator` ne doit jamais envoyer d'email réel — uniquement EHLO/MAIL FROM/RCPT TO/QUIT
3. Si SerpApi absent → fallback Ollama silencieux (pas d'erreur fatale)
4. Les leads avec `heat_score < 4` sont rejetés avant le PageSpeed (économie de quota API)
