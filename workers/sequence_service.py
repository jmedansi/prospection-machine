import subprocess
import sys
import os
import time
import logging
from threading import Thread

"""
Service pour lancer automatiquement le worker de relances (sequence_worker.py)
- Démarre le worker toutes les heures en tâche de fond
- Redémarre en cas d'erreur
- Peut être lancé au boot (ex: via start_machine.bat)
"""

LOG_PATH = os.environ.get('SEQUENCE_SERVICE_LOG', 'sequence_service.log')

logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s'
)

WORKER_CMD = [sys.executable, '-m', 'workers.sequence_worker']
INTERVAL_SECONDS = 3600  # 1h


def run_worker_loop():
    while True:
        try:
            logging.info('Lancement du worker de relances...')
            proc = subprocess.Popen(WORKER_CMD)
            proc.wait()
            if proc.returncode == 0:
                logging.info('Worker terminé avec succès.')
            else:
                logging.error(f'Worker terminé avec code {proc.returncode}')
        except Exception as e:
            logging.error(f'Erreur lors du lancement du worker: {e}')
        logging.info(f'Attente {INTERVAL_SECONDS // 60} min avant prochain run...')
        time.sleep(INTERVAL_SECONDS)


def start_service():
    t = Thread(target=run_worker_loop, daemon=True)
    t.start()
    logging.info('Service de relances automatiques démarré.')
    t.join()

if __name__ == '__main__':
    start_service()
