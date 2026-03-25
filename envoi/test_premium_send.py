# -*- coding: utf-8 -*-
"""
Test d'envoi de l'email Premium HTML.
"""
import sys
import os

# Ajout de la racine au path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from envoi.resend_sender import send_prospecting_email
from envoi.email_builder import build_premium_email

def test_premium_send():
    prospect_email = "jmedansi@incidenx.com"
    prospect_nom = "Hôtel de France (Test Premium)"
    objet = "Une opportunité pour Hôtel de France 🚀"
    
    # Corps type Jean-Marc S1_LENT
    corps = "Bonjour,\n\nJ'ai testé Hôtel de France sur mobile ce matin.\n12.5 secondes avant que la page s'affiche.\n\n53% des visiteurs partent avant 3 secondes.\nVos concurrents chargent en 2s.\nChaque jour, vous perdez la moitié de vos visites mobiles.\n\nOn en parle 15 minutes ?\n\nJean-Marc"
    
    lien = "https://audit.incidenx.com/hotel-de-france-test"
    mockup = "https://audit.incidenx.com/hotel-de-france/mockup.png" # URL placeholder réaliste

    print("Génération de l'HTML Premium...")
    html_content = build_premium_email({
        'prospect_nom': prospect_nom,
        'email_objet': objet,
        'email_corps': corps,
        'lien_rapport': lien,
        'mockup_url': mockup
    })

    # Sauvegarde locale pour debug visuel rapide (optionnel)
    with open('premium_preview.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    print("Aperçu généré dans premium_preview.html")

    print(f"Tentative d'envoi à {prospect_email}...")
    result = send_prospecting_email(
        prospect_email=prospect_email,
        prospect_nom=prospect_nom,
        email_objet=objet,
        email_corps=html_content,
        dry_run=False
    )
    
    if result["success"]:
        print(f"✅ Succès ! Message ID: {result['message_id']}")
    else:
        print(f"❌ Échec : {result['erreur']}")

if __name__ == "__main__":
    test_premium_send()
