---
module: sniper/bodacc_scanner.py
---

# sniper/bodacc_scanner.py — Source BODACC : nominations de dirigeants

## Rôle
Scanne quotidiennement le BODACC (Bulletin Officiel Des Annonces Civiles
et Commerciales) pour détecter les nouvelles nominations de dirigeants dans
des entreprises B2B digitales françaises.

Chaque lead inséré contient le **nom du CEO** extrait directement depuis
l'annonce officielle — pas besoin de `ceo_finder.py` sur ces leads.

## Flux
```
scan_daily(date=hier)
  → BODACC API  ← annonces "Modification" + "Immatriculation"
  → _extract_siren()         ← extrait SIREN depuis champ registre
  → _parse_dirigeants()      ← filtre qualités CEO/Gérant/Président
  → _resolve_company(siren)  ← API recherche-entreprises.api.gouv.fr
  → filtre NAF               ← B2B digital uniquement (voir TARGET_NAF)
  → _insert_bodacc_lead()    ← INSERT leads_bruts source='bodacc'
```

## Sources API utilisées
| API | URL | Auth |
|---|---|---|
| BODACC OpenData | `bodacc-datadila.opendatasoft.com` | Aucune |
| API Entreprises | `recherche-entreprises.api.gouv.fr` | Aucune |

Les deux sont **gratuites et sans clé**.

## Codes NAF ciblés (B2B digital)
`6201Z` à `6209Z` (informatique) · `7311Z`/`7312Z` (publicité) ·
`7022Z`/`7021Z` (conseil) · `6311Z`/`6312Z` (data/cloud) · `5829*` (édition logiciel)

## Données injectées dans donnees_audit (JSON)
| Clé | Source |
|---|---|
| `ceo_prenom` | BODACC acte.dirigeants.prenoms |
| `ceo_nom` | BODACC acte.dirigeants.nom |
| `ceo_source` | `"bodacc"` (toujours) |
| `naf` | API Entreprises siege.activite_principale |
| `siren` | Champ registre BODACC |
| `qualite` | Qualité du dirigeant (Gérant, Président…) |

## Scheduler
`dashboard/scheduler.py` — job `bodacc_daily_scan` tous les jours à **07:00**.
BODACC publie le journal de J-1 entre 06:00 et 07:00.

## Route API
- `POST /api/sniper/bodacc-scan` — scan manuel avec `{"date": "2026-04-10"}` (optionnel)

## Connexion email_generator
`sniper/email_generator.py` → `SNIPER_SOURCES` inclut `'bodacc'`.
Les leads BODACC sans `tag_urgence` passent par `email_generator`
**uniquement après** que le pipeline Sniper Phase 2 (PageSpeed + Wappalyzer)
les a enrichis et a positionné `tag_urgence` + `niveau_urgence`.

## Règles
- Ne pas insérer si `site_web` est vide — sans site, pas d'audit possible
- Déduplication sur SIREN : un même SIREN ne peut avoir qu'un lead actif (`source='bodacc'`)
- `niveau_urgence` reste à `0` à l'insertion — le scoring Sniper le positionnera
- Ne jamais augmenter `_PAGE_SIZE` au-dessus de 100 (limite API BODACC)
