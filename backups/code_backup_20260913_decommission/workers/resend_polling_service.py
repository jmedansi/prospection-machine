"""
Service de polling Resend - récupère les événements d'email via l'API Resend.
À exécuter toutes les minutes via un scheduler ou cron.

Commande: python -m workers.resend_polling_service
"""

import os
import requests
from datetime import datetime, timedelta
from database.db_manager import get_conn, update_email_tracking
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

RESEND_API_KEY = os.getenv('RESEND_API_KEY', '')

def poll_resend_events():
    """
    Récupérer les statuts des emails depuis notre BD et vérifier via l'API Resend.
    Mettre à jour la BD avec les ouvertures, clics, bounces.
    """
    if not RESEND_API_KEY:
        logger.error("RESEND_API_KEY non configurée")
        return

    try:
        # Récupérer tous les emails envoyés depuis notre BD (derniers 30 jours)
        with get_conn() as conn:
            thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()

            emails = conn.execute("""
                SELECT id, message_id_resend, email_destinataire, date_envoi
                FROM emails_envoyes
                WHERE message_id_resend IS NOT NULL
                  AND date_envoi > ?
                  AND (ouvert = 0 OR clique = 0)
                LIMIT 100
            """, (thirty_days_ago,)).fetchall()

        logger.info(f"Vérification de {len(emails)} emails auprès de Resend")

        # Vérifier le statut de chaque email via l'API Resend
        for email_row in emails:
            email_id, message_id_resend, email_addr, date_envoi = email_row
            _check_email_status(message_id_resend, email_id)

        logger.info("✅ Polling Resend complété")

    except Exception as e:
        logger.error(f"Erreur lors du polling: {e}")

def _check_email_status(message_id_resend: str, email_row_id: int):
    """
    Récupérer le statut d'un email via l'API Resend.
    Mettre à jour notre BD avec les dernières informations.
    """
    try:
        response = requests.get(
            f'https://api.resend.com/emails/{message_id_resend}',
            headers={'Authorization': f'Bearer {RESEND_API_KEY}'},
            timeout=10
        )

        if response.status_code != 200:
            logger.warning(f"Email {message_id_resend} non trouvé (status {response.status_code})")
            return

        email_data = response.json()

        # Statut du email
        status = email_data.get('status')

        if status == 'delivered':
            update_email_tracking(message_id_resend, {'statut_envoi': 'delivered'})

        elif status == 'bounced':
            reason = email_data.get('reason', 'unknown')
            update_email_tracking(message_id_resend, {
                'bounce': 1,
                'statut_envoi': 'bounce_hard' if 'hard' in reason.lower() else 'bounce_soft'
            })

        elif status == 'complained':
            update_email_tracking(message_id_resend, {'statut_envoi': 'complained'})

        # Vérifier les événements détaillés
        events = email_data.get('events', [])

        if events:
            # Compter les ouvertures
            opened = [e for e in events if e.get('type') == 'opened']
            if opened:
                latest_open = opened[-1].get('created_at')
                update_email_tracking(message_id_resend, {
                    'ouvert': 1,
                    'date_ouverture': latest_open,
                    'nb_ouvertures': len(opened)
                })
                logger.info(f"👁️ Email {message_id_resend[:20]}... ouvert {len(opened)}x")

            # Compter les clics
            clicked = [e for e in events if e.get('type') == 'clicked']
            if clicked:
                latest_click = clicked[-1].get('created_at')
                update_email_tracking(message_id_resend, {
                    'clique': 1,
                    'date_clic': latest_click
                })
                logger.info(f"🔗 Email {message_id_resend[:20]}... cliqué {len(clicked)}x")

    except Exception as e:
        logger.error(f"Erreur vérification {message_id_resend}: {e}")

if __name__ == '__main__':
    poll_resend_events()
