# -*- coding: utf-8 -*-
"""
Test de l'envoi via Resend.
"""
import sys
import os

# Ajout de la racine au path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from envoi.resend_sender import send_prospecting_email

def test_resend():
    prospect_email = "jmedansi@incidenx.com" # Test sur l'email de l'utilisateur
    prospect_nom = "Test Resend"
    objet = "Test de Tracking Prospection 🚀"
    corps = """
    Bonjour Jean-Marc,<br><br>
    Ceci est un test réel pour valider le tracking de ton outil.<br>
    <a href="https://incidenx.com" style="color: #10b981; font-weight: bold;">Clique ici pour tester le suivi du clic</a><br><br>
    Si tu reçois ce mail, l'envoi fonctionne. Si tu cliques, on saura si le tracking est OK !
    """
    
    print(f"Tentative d'envoi à {prospect_email}...")
    result = send_prospecting_email(
        prospect_email=prospect_email,
        prospect_nom=prospect_nom,
        email_objet=objet,
        email_corps=corps,
        dry_run=False
    )
    
    if result["success"]:
        print(f"✅ Succès ! Message ID: {result['message_id']}")
        # Enregistrement en base pour permettre le tracking
        from database.db_manager import insert_email_sent
        try:
            insert_email_sent({
                'lead_id': 1, # ID arbitraire pour le test
                'message_id_resend': result['message_id'],
                'email_objet': objet,
                'email_corps': corps,
                'statut_envoi': 'test_tracking'
            })
            print("📊 Enregistré en base pour le tracking.")
        except Exception as e:
            print(f"⚠️ Erreur insertion base : {e}")
    else:
        print(f"❌ Échec : {result['erreur']}")

if __name__ == "__main__":
    test_resend()
