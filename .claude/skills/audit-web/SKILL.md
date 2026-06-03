---
name: audit-web
description: Activated when modifying or debugging any file in auditeur/. Provides rules for web auditing, PageSpeed extraction, BeautifulSoup parsing, and scoring logic.
---

# Règles pour l'agent Auditeur

## PageSpeed Insights
- Toujours appeler strategy=mobile ET strategy=desktop
- Extraire EXACTEMENT ces champs et pas d'autres :
  categories.performance.score × 100
  audits.largest-contentful-paint.numericValue
  audits.cumulative-layout-shift.numericValue
  audits.first-contentful-paint.numericValue
  audits.render-blocking-resources.details.items (length)
  audits.uses-long-cache-ttl.score
  audits.total-byte-weight.numericValue / 1024
- Si l'API retourne une erreur → score = -1, logger l'URL

## BeautifulSoup
- Toujours utiliser features="html.parser" (pas lxml)
- Toujours encapsuler le fetch dans try/except avec timeout=10
- Toujours vérifier que soup n'est pas None avant de parser
- Pour détecter Schema.org : regex sur json-ld uniquement

## Scoring
- La fonction calculate_score() ne doit JAMAIS appeler un LLM
- Le score est un entier entre 0 et 10
- get_top3_problems() retourne exactement 3 éléments, jamais plus
- Les problèmes sont triés par impact décroissant (3 > 2 > 1)

## Gestion des sites hors-ligne
- Si requests.get() timeout → statut = "site_inaccessible"
- Si status_code != 200 → statut = "erreur_http_{code}"
- Dans les deux cas → score_priorite = 0, continuer au lead suivant
