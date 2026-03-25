# -*- coding: utf-8 -*-
"""
Diagnostic Resend — affiche la réponse JSON complète.
Lance : python envoi/diag_resend.py
"""

import os
import sys
import json
import requests
from dotenv import load_dotenv

# Charger le .env depuis la racine du projet
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

resend_key   = os.getenv("RESEND_API_KEY")
sender_email = os.getenv("BREVO_SENDER_EMAIL")
sender_name  = os.getenv("BREVO_SENDER_NAME")

print("\n=== DIAGNOSTIC RESEND ===\n")
print(f"RESEND_API_KEY    : {'...'+resend_key[-8:] if resend_key else '❌ MANQUANTE'}")
print(f"SENDER_EMAIL     : {sender_email or '❌ MANQUANTE'}")
print(f"SENDER_NAME      : {sender_name or '❌ MANQUANTE'}")
print()

if not resend_key:
    print("❌ Clé API manquante dans .env. Abandon.")
    sys.exit(1)

# Appel API direct
url = "https://api.resend.com/emails"
headers = {
    "Authorization": f"Bearer {resend_key}",
    "Content-Type": "application/json"
}

# Resend nécessite onboarding@resend.dev si le domaine n'est pas vérifié
from_email = f"{sender_name} <onboarding@resend.dev>" if "resend.dev" in str(sender_email) else f"{sender_name} <{sender_email}>"

payload = {
    "from": from_email,
    "to": ["jmedansi@incidenx.com"],
    "subject": "[DIAG] Test connexion Resend",
    "html": "<p>Test de diagnostic — Machine de Prospection Incidenx configurée sur <strong>Resend</strong>.</p>"
}

print(f"Envoi depis {from_email} vers jmedansi@incidenx.com ...\n")
try:
    resp = requests.post(url, json=payload, headers=headers, timeout=15)
    print(f"Status HTTP : {resp.status_code}")
    
    if resp.text:
        print(f"Réponse complète :\n{json.dumps(resp.json(), indent=2, ensure_ascii=False)}")
    else:
        print("Pas de corps de réponse.")

    if resp.status_code in (200, 201):
        print("\n✅ Email envoyé avec succès !")
    else:
        print("\n❌ Erreur Resend — voir réponse ci-dessus")

except Exception as e:
    print(f"\n❌ Exception : {e}")
