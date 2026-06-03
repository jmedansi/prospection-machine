---
module: sniper/imap_poller.py
---

# sniper/imap_poller.py — Détection des réponses (step 1)

## Rôle
Scanne la boîte `jmedansi@incidenx.com` toutes les 15 minutes pour détecter
les réponses aux emails Sniper step 1.  
Quand une réponse est trouvée → notification Telegram + bouton "Envoyer step 2".

## Flux
```
IMAP UNSEEN (48h)
  → filtre OOO / bounces / auto-replies
  → match sender email → leads_audites.email_valide (ou domain fallback)
  → UPDATE statut_prospection = 'repondu'
  → notify Telegram (callback sniper_step2_{audit_id})
  → IMAP SEEN
```

## Fonctions publiques
| Fonction | Description |
|---|---|
| `run_poll(lookback_hours=48)` | Scan principal — appelé par le scheduler |
| `send_step2(audit_id)` | Envoie email_step2_livraison.html via Resend |

## Configuration .env
```
IMAP_HOST=mail.incidenx.com
IMAP_PORT=993
IMAP_USER=jmedansi@incidenx.com
IMAP_PASSWORD=...
CALENDLY_URL=https://calendly.com/jmedansi   (optionnel)
```

## Appel scheduler
`dashboard/scheduler.py` — job `sniper_imap_poll` toutes les 15 min.

## Route API
- `POST /api/sniper/poll-imap` — poll manuel (test)
- `POST /api/sniper/send-step2` — envoi step 2 manuel `{"audit_id": 42}`

## Règles
- Ne jamais modifier le comportement OOO sans mettre à jour `_OOO_PATTERNS`
- `send_step2` est idempotent : si `statut_prospection='lien_envoye'`, abandon
- Réutilise `envoi/resend_sender.send_prospecting_email` — pas de nouvel expéditeur
