# -*- coding: utf-8 -*-
"""
envoi/test_webhook.py — Simulateur de webhooks Resend
Permet de tester l'endpoint /webhooks/resend sans envoyer de vrais mails.
"""

import requests
import json
import time
from datetime import datetime

# URL locale du dashboard (à adapter si besoin)
WEBHOOK_URL = "http://localhost:5001/webhooks/resend"

def simulate_event(event_type, email_id):
    """Envoie un faux payload Resend à l'endpoint local."""
    payload = {
        "type": event_type,
        "created_at": datetime.now().isoformat(),
        "data": {
            "email_id": email_id,
            "from": "test@resend.dev",
            "to": ["prospect@example.com"],
            "subject": "Test Webhook"
        }
    }
    
    print(f"📡 Simulation de l'événement : {event_type} pour ID {email_id}...")
    try:
        # Note: On ne met pas de signature svix ici car le serveur 
        # local ne vérifie que si RESEND_WEBHOOK_SECRET est présent dans le .env
        r = requests.post(WEBHOOK_URL, json=payload, timeout=5)
        if r.status_code == 200:
            print(f"✅ Succès : {r.json()}")
        else:
            print(f"❌ Erreur {r.status_code} : {r.text}")
    except Exception as e:
        print(f"❌ Erreur de connexion : {e}")

if __name__ == "__main__":
    # 1. On récupère un message_id existant en base pour le test
    # (Ou on en crée un faux si la base est vide)
    print("🔍 Recherche d'un message_id en base pour le test...")
    
    # Pour le test, on va juste utiliser un ID arbitraire 'test-message-123'
    # Il faudra qu'il existe dans la table emails_envoyes.message_id_brevo
    # pour que l'update SQLite fonctionne réellement.
    
    test_id = "test-resend-id-999"
    
    # On simule une suite d'événements
    simulate_event("email.delivered", test_id)
    time.sleep(1)
    simulate_event("email.opened", test_id)
    time.sleep(1)
    simulate_event("email.clicked", test_id)
    
    print("\n🏁 Tests terminés. Vérifie le Dashboard (onglet Suivi) !")
