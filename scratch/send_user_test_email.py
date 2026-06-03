# -*- coding: utf-8 -*-
import sys
import os

# Add project root to sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from envoi.resend_sender import send_prospecting_email

def main():
    print("=== SENDING TEST EMAIL TO USER ===")
    
    test_recipient = "jmedansi@gmail.com"  # Your test address
    test_subject = "Test de Prospection Machine - Resend Configuré !"
    test_body = """
    <html>
        <body>
            <h2 style="color: #4f46e5;">Bravo Jean-Marc !</h2>
            <p>La Prospection Machine est désormais configurée avec votre véritable clé Resend.</p>
            <p>Le bug d'authentification a été corrigé et les envois vont pouvoir partir normalement.</p>
            <br>
            <p>-- Antigravity, votre agent d'élite</p>
        </body>
    </html>
    """
    
    print(f"Sending test email to: {test_recipient}")
    result = send_prospecting_email(
        prospect_email=test_recipient,
        prospect_nom="Jean-Marc",
        email_objet=test_subject,
        email_corps=test_body,
        lien_rapport="https://audit.incidenx.com/test",
        dry_run=False
    )
    
    print(f"\nResult: {result}")

if __name__ == '__main__':
    main()
