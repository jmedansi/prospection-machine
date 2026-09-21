---
module: sniper/rapport_generator.py
---

# sniper/rapport_generator.py — Génération et publication du rapport d'audit

## Rôle
Génère une page HTML professionnelle à partir des données PageSpeed/CMS d'un lead Sniper
et la publie sur `audit.incidenx.com/{slug}/` via l'infra GitHub/Vercel existante.

Le lien est envoyé dans l'email **step 2** (après réponse du prospect).

## Flux
```
generate_and_publish(lead_id)
  → lit lb.donnees_audit (PageSpeed + CMS) + leads_audites
  → generate_sniper_rapport_html()  ← HTML ~7Ko
  → push_audit_to_github(slug, html)  ← batch commit → Vercel
  → UPDATE leads_audites.lien_rapport = "https://audit.incidenx.com/{slug}/"
```

## Données utilisées depuis donnees_audit (JSON)
| Clé | Description |
|---|---|
| `score_mobile` | Score PageSpeed mobile (0-100) |
| `lcp_ms` | Largest Contentful Paint en ms |
| `fcp_ms` | First Contentful Paint en ms |
| `render_blocking_scripts` | Nombre de scripts bloquants |
| `page_size_kb` | Poids total de la page |
| `cms` / `ecommerce` | CMS détecté (WordPress, Shopify…) |
| `server` | Serveur HTTP (Apache, Nginx…) |
| `has_cdn` / `has_waf` / `has_https` | Infra réseau |
| `reason` | Phrase d'explication du score |

## Angle narrative par tag
- `perf` → angle ROAS / campagnes Google Ads
- `securite` → angle risque infrastructure / DDoS
- `perf+securite` → double impact

## Appel depuis email_generator
`sniper/email_generator.py` lance `generate_and_publish` en thread daemon
après chaque INSERT dans leads_audites. Non bloquant.

## Configuration .env
```
GITHUB_TOKEN=...
GITHUB_BRANCH=main
VERCEL_TOKEN=...
VERCEL_PROJECT_NAME=incidenx-audit
AUDIT_DOMAIN=audit.incidenx.com
CALENDLY_URL=https://calendly.com/jmedansi
```

## Règles
- Réutilise `synthetiseur/github_publisher.push_audit_to_github()` — pas de duplication
- Le rapport est `noindex,nofollow` — confidentiel, pas indexé Google
- Le slug est basé sur le domaine : `dupont-solar.fr` → `dupont-solar-fr`
