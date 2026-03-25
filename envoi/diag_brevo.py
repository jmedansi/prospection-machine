# -*- coding: utf-8 -*-
"""
Diagnostic Brevo — affiche la réponse JSON complète.
Lance : python envoi/diag_brevo.py
"""

import os
import sys
import json
import requests
from dotenv import load_dotenv

# Charger le .env depuis la racine du projet
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

brevo_key    = os.getenv("BREVO_API_KEY")
sender_email = os.getenv("BREVO_SENDER_EMAIL")
sender_name  = os.getenv("BREVO_SENDER_NAME")

print("\n=== DIAGNOSTIC BREVO ===\n")
print(f"BREVO_API_KEY     : {'...'+brevo_key[-8:] if brevo_key else '❌ MANQUANTE'}")
print(f"BREVO_SENDER_EMAIL: {sender_email or '❌ MANQUANTE'}")
print(f"BREVO_SENDER_NAME : {sender_name or '❌ MANQUANTE'}")
print()

if not brevo_key:
    print("❌ Clé API manquante dans .env. Abandon.")
    sys.exit(1)

# Appel API direct
url = "https://api.brevo.com/v3/smtp/email"
headers = {
    "accept": "application/json",
    "api-key": brevo_key,
    "content-type": "application/json"
}
payload = {
    "sender": {"name": sender_name, "email": sender_email},
    "to": [{"email": "jmedansi@incidenx.com", "name": "Jean-Marc DANSI"}],
    "subject": "[DIAG] Test connexion Brevo",
    "textContent": "Test de diagnostic — Machine de Prospection Incidenx."
}

print("Envoi vers jmedansi@incidenx.com ...\n")
try:
    resp = requests.post(url, json=payload, headers=headers, timeout=15)
    print(f"Status HTTP : {resp.status_code}")
    print(f"Réponse complète :\n{json.dumps(resp.json(), indent=2, ensure_ascii=False)}")

    if resp.status_code in (200, 201):
        print("\n✅ Email envoyé !")
    else:
        print("\n❌ Erreur Brevo — voir réponse ci-dessus")

except Exception as e:
    print(f"\n❌ Exception : {e}")
