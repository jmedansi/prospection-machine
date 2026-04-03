"""
Scheduler pour exécuter le polling Resend toutes les minutes.

Commande: python -m workers.scheduler
"""

import time
import logging
import schedule
from workers.resend_polling_service import poll_resend_events

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def job():
    """Job à exécuter"""
    logger.info("🔄 Lancement du polling Resend...")
    poll_resend_events()

if __name__ == '__main__':
    logger.info("📅 Scheduler démarré - Polling Resend chaque minute")

    # Planifier le job
    schedule.every(1).minutes.do(job)

    # Exécuter une première fois immédiatement
    job()

    # Boucle infinie
    while True:
        schedule.run_pending()
        time.sleep(10)  # Vérifier toutes les 10 secondes
