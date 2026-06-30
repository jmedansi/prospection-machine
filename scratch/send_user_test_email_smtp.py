# -*- coding: utf-8 -*-
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from envoi.smtp_sender import send_prospecting_email_smtp


def main():
    print('=== TEST SMTP SEND ===')
    recipient = 'jmedansi@gmail.com'
    subject = 'Test de la boîte mail SMTP directe'
    body = '''
    <html>
        <body>
            <h2>Test SMTP direct</h2>
            <p>Ceci est un test d'envoi direct depuis votre boîte mail via le module SMTP.</p>
            <p>Si l'email est reçu, la configuration SMTP est correcte.</p>
        </body>
    </html>
    '''

    result = send_prospecting_email_smtp(
        prospect_email=recipient,
        prospect_nom='Jean-Marc',
        email_objet=subject,
        email_corps=body,
        lien_rapport='https://audit.incidenx.com/test',
        dry_run=False,
    )

    print('Result:', result)


if __name__ == '__main__':
    main()
