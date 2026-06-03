# -*- coding: utf-8 -*-
"""
workers/sequence_worker.py
Worker pour les sequences de relances planifiees.

Nouveau flux (validation Telegram) :
  1. Recupere les sequences 'planned' arrivees a echeance
  2. Verifie les conditions (should_send_sequence)
  3. Met a jour le score du lead
  4. Genere le contenu email et stocke dans email_sequences
  5. Passe le statut a 'pending_approval'
  6. Envoie une notification Telegram pour approbation

L'envoi effectif est realise par le poller (scheduler) qui surveille
les reponses ✅ de l'utilisateur.

Commande: python -m workers.sequence_worker
"""

import logging
from datetime import datetime
from services.email_sequence_service import EmailSequenceService
from services.lead_scoring_service import LeadScoringService

logger = logging.getLogger(__name__)


def run_sequence_worker():
    logger.info(f"[SequenceWorker] Demarrage a {datetime.now().isoformat()}")
    seq_service = EmailSequenceService()
    scoring_service = LeadScoringService()

    sequences = seq_service.get_sequences_to_process()
    logger.info(f"[SequenceWorker] {len(sequences)} sequences a traiter")

    for seq in sequences:
        lead_id = seq['lead_id']
        sequence_id = seq['id']
        email_type = seq['email_type']

        # 1. Mettre a jour le score
        try:
            score, temperature = scoring_service.update_lead_score(lead_id)
            logger.debug(f"[SequenceWorker] Lead {lead_id} score={score} temp={temperature}")
        except Exception as e:
            logger.debug(f"[SequenceWorker] Score update failed for {lead_id}: {e}")

        # 2. Verifier les conditions
        if not seq_service.should_send_sequence(seq):
            logger.info(f"[SequenceWorker] Skip sequence {sequence_id} (condition non remplie)")
            continue

        # 3. Generer le contenu + demander validation Telegram
        ok = seq_service.generate_and_request_approval(seq)
        if ok:
            logger.info(
                f"[SequenceWorker] Sequence {sequence_id} ({email_type}) "
                f"envoyee pour approbation (lead {lead_id})"
            )
        else:
            logger.error(
                f"[SequenceWorker] Echec generation approbation pour "
                f"sequence {sequence_id}"
            )

    logger.info(f"[SequenceWorker] Termine ({len(sequences)} sequences)")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run_sequence_worker()
