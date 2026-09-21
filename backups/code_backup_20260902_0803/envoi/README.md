# Module `envoi/` — Expédition d'Emails (Resend & Brevo)

Envoi transactionnel des emails de prospection via l'API Brevo.

## Fichiers

| Fichier | Rôle |
|---|---|
| `resend_sender.py` | Nouveau module d'envoi via **Resend** (Défaut) |
| `brevo_sender.py` | Module legacy via Brevo |
| `diag_resend.py` | Outil de diagnostic Resend |
| `test_resend.py` | Script de test Resend |

## Utilisation

```python
from resend_sender import send_prospecting_email  # ou brevo_sender

result = send_prospecting_email(
    prospect_email="contact@restaurant.fr",
    prospect_nom="Restaurant Le Midi",
    email_objet="votre site met 6s à charger sur mobile",
    email_corps="...",
    lien_rapport="https://audit.incidenx.com/...",
    dry_run=False
)
```

## Variables `.env` requises

```
RESEND_API_KEY=re_...
BREVO_API_KEY=xkeysib-...
BREVO_SENDER_EMAIL=jmedansi@incidenx.com
BREVO_SENDER_NAME=Jean-Marc DANSI
```

## Test

```bash
python envoi/test_brevo.py
```
