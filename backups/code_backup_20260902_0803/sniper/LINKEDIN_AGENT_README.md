---
module: sniper/linkedin_agent.py
---

# sniper/linkedin_agent.py — Canal LinkedIn (omnicanalité catch-all)

## Rôle
Quand un lead a `is_catch_all=True` (email non vérifiable) **et** un CEO identifié,
bascule sur LinkedIn : demande de connexion + message d'accroche via Patchright.

Message type :
> *"J'ai tenté de vous faire parvenir un audit technique par e-mail,
> mais l'acheminement était impossible côté serveur. Je vous le dépose ici..."*

## Flux
```
catch-all détecté + ceo_prenom/nom disponibles
  → _get_available_account()  ← rotation multi-comptes
  → Patchright login LinkedIn
  → _search_linkedin_profile()  ← recherche interne LinkedIn
  → navigation profil → bouton "Se connecter"
  → frappe message caractère par caractère (anti-détection)
  → UPDATE statut_prospection = 'linkedin_envoye'
  → Telegram notif
```

## Multi-comptes
```
LINKEDIN_EMAIL_1=...   LINKEDIN_PASSWORD_1=...
LINKEDIN_EMAIL_2=...   LINKEDIN_PASSWORD_2=...
LINKEDIN_DAILY_LIMIT=15   ← par compte (total = N × 15)
```
Rotation automatique : compte 1 jusqu'à sa limite, puis compte 2, etc.

## Fonctions publiques
| Fonction | Description |
|---|---|
| `send_linkedin_outreach(...)` | Point d'entrée — appelé par pipeline.py |
| `get_daily_stats()` | Stats envoi du jour par compte (dashboard) |

## Limites de sécurité
- Max 15 connexions/compte/jour (LinkedIn anti-bot)
- Abandon immédiat si checkpoint/CAPTCHA au login
- Comptes doivent être "chauds" (ancienneté + activité)

## Appel depuis pipeline
`scraper/sniper/pipeline.py` → `_score_and_store()` — thread daemon si catch-all.

## Règles
- Ne jamais augmenter LINKEDIN_DAILY_LIMIT au-dessus de 20 sans compte vérifié
- La recherche profil se fait dans la session connectée (pas Google/DDG)
- `linkedin_url` stocké dans `leads_audites.linkedin_url`
