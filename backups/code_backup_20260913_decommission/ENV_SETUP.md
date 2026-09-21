# ENV_SETUP.md — Variables d'environnement

État au 2026-04-12. Toutes les variables sont dans `.env` à la racine du projet.

---

## Statut global

| Bloc | Statut |
|------|--------|
| Email (Resend + IMAP) | ✅ Configuré |
| Rapports (GitHub + Vercel) | ✅ Configuré |
| CEO Finder Groq | ✅ Configuré |
| Source 3 France Travail | ✅ Configuré |
| LinkedIn catch-all | ⚠️ Compte à réchauffer (3 semaines) |
| Source 1 Ads / Source 2 Tech / BODACC | ✅ Aucune clé requise |

---

## Détail par bloc

### Email — Resend
| Variable | Valeur | Rôle |
|----------|--------|------|
| `RESEND_API_KEY` | `re_16t3...` | Envoi emails Maps + Sniper step 1 |
| `RESEND_WEBHOOK_SECRET` | `whsec_...` | Vérification webhooks tracking |

### Email — IMAP (détection réponses Sniper)
| Variable | Valeur | Rôle |
|----------|--------|------|
| `IMAP_HOST` | `mail.incidenx.com` | Serveur LWS |
| `IMAP_PORT` | `993` | SSL |
| `IMAP_USER` | `jmedansi@incidenx.com` | Boîte de réception step 1 |
| `IMAP_PASSWORD` | `***` | |

### Rapports audit — GitHub + Vercel
| Variable | Valeur | Rôle |
|----------|--------|------|
| `GITHUB_TOKEN` | `ghp_...` | Push HTML vers `jmedansi/incidenx-audit` |
| `VERCEL_TOKEN` | `vcp_...` | Déploiement automatique |
| `VERCEL_PROJECT_ID` | `prj_...` | ID projet Vercel |
| `VERCEL_ORG_ID` | `m3fr...` | ID organisation Vercel |
| `VERCEL_PROJECT_NAME` | `incidenx-audit` | Nom projet |
| `AUDIT_DOMAIN` | `audit.incidenx.com` | Domaine public des rapports |

### CEO Finder — Groq (cloud LLM fallback)
| Variable | Valeur | Rôle |
|----------|--------|------|
| `GROQ_API_KEY` | `gsk_...` | Modèle `llama-3.1-8b-instant`, après API gouv.fr |

Chaîne complète : **API gouv.fr** (gratuit, FR) → **Groq** (cloud, 30k tokens/min gratuit) → **Ollama** (local).

### Source 3 — France Travail (offres d'emploi)
| Variable | Valeur | Rôle |
|----------|--------|------|
| `FT_CLIENT_ID` | `PAR_offres...` | OAuth2 client ID |
| `FT_CLIENT_SECRET` | `5461...` | OAuth2 secret |

Scope configuré : `api_offresdemploiv2 o2dsoffre`.
Token TTL : 25 min, renouvelé automatiquement.

### LinkedIn — Canal catch-all (Patchright)
| Variable | Valeur | Rôle |
|----------|--------|------|
| `LINKEDIN_EMAIL_1` | `jmedansi@gmail.com` | Compte 1 |
| `LINKEDIN_PASSWORD_1` | `***` | |
| `LINKEDIN_DAILY_LIMIT` | `15` | Max envois/compte/jour (ne pas dépasser 20) |

> Compte personnel avec plusieurs années d'ancienneté — profil établi, pas de période de chauffe requise.

Compte 2 : décommenter `LINKEDIN_EMAIL_2` / `LINKEDIN_PASSWORD_2` dans `.env` quand disponible.

### Calendly
| Variable | Valeur | Rôle |
|----------|--------|------|
| `CALENDLY_URL` | `https://calendly.com/jmedansi` | Lien RDV dans rapports HTML + emails step 2 |

### Divers (ancien pipeline)
| Variable | Rôle |
|----------|------|
| `GOOGLE_SHEETS_ID` | Export leads vers Google Sheets |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Chemin vers le JSON service account |
| `HUNTER_API_KEY` | Recherche emails (pipeline Maps) |
| `BREVO_API_KEY` | Ancien expéditeur (remplacé par Resend) |
| `NGROK_AUTHTOKEN` / `NGROK_DOMAIN` | Tunnel local pour webhooks en dev |

---

## Variables sans clé requise

Ces sources/modules fonctionnent sans configuration supplémentaire :

| Module | Pourquoi |
|--------|----------|
| Source 1 Ads | Google Ads scraping via Playwright — pas d'API key |
| Source 2 Tech | API recherche-entreprises.api.gouv.fr — gratuite, sans auth |
| BODACC scanner | API BODACC OpenData — gratuite, sans auth |
| CEO Finder (API gouv.fr) | API recherche-entreprises — gratuite, sans auth |
| Ollama (CEO fallback local) | Modèle local, pas de clé |

---

## Vérification rapide

```bash
python -c "
import os; from dotenv import load_dotenv; load_dotenv()
checks = {
    'RESEND_API_KEY':    os.getenv('RESEND_API_KEY'),
    'IMAP_PASSWORD':     os.getenv('IMAP_PASSWORD'),
    'GITHUB_TOKEN':      os.getenv('GITHUB_TOKEN'),
    'GROQ_API_KEY':      os.getenv('GROQ_API_KEY'),
    'FT_CLIENT_ID':      os.getenv('FT_CLIENT_ID'),
    'LINKEDIN_EMAIL_1':  os.getenv('LINKEDIN_EMAIL_1'),
    'CALENDLY_URL':      os.getenv('CALENDLY_URL'),
}
for k, v in checks.items():
    print(f'  {\"OK\" if v else \"MANQUE\"} {k}')
"
```
