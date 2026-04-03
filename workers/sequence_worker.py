#!/usr/bin/env python
"""
Worker pour exécuter les séquences de relances planifiées.
À exécuter toutes les heures via cron ou un scheduler.

Commande: python -m workers.sequence_worker
"""
import os
import sqlite3
from datetime import datetime
from services.email_sequence_service import EmailSequenceService
from services.lead_scoring_service import LeadScoringService
from envoi.resend_sender_with_retry import ResendSenderWithRetry

DB_PATH = os.environ.get('DB_PATH', 'data/prospection.db')
RESEND_API_KEY = os.environ.get('RESEND_API_KEY', 'changeme')


def run_sequence_worker():
    print(f"[SequenceWorker] Démarrage à {datetime.now().isoformat()}")
    seq_service = EmailSequenceService(DB_PATH)
    scoring_service = LeadScoringService(DB_PATH)
    sender = ResendSenderWithRetry(RESEND_API_KEY, DB_PATH)

    # 1. Récupérer les séquences prêtes à être envoyées
    sequences = seq_service.get_sequences_to_send()
    print(f"[SequenceWorker] {len(sequences)} séquences à traiter")

    for seq in sequences:
        lead_id = seq['lead_id']
        sequence_id = seq['id']
        email_record_id = seq['email_record_id']
        email_type = seq['email_type']

        # 2. Mettre à jour le score du lead avant d'envoyer
        score, temperature = scoring_service.update_lead_score(lead_id)
        print(f"[SequenceWorker] Lead {lead_id} score={score} temp={temperature}")

        # 3. Vérifier si la séquence doit être envoyée (conditions)
        if not seq_service.should_send_sequence(seq):
            print(f"[SequenceWorker] Skip sequence {sequence_id} (condition non remplie)")
            continue

        # 4. Générer le contenu de la relance (utiliser email_builder)
        from envoi.email_builder import build_premium_email
        # Récupérer les infos du lead/email (à adapter selon votre modèle)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM emails_envoyes WHERE id = ?", (email_record_id,))
        email_row = cursor.fetchone()
        conn.close()
        if not email_row:
            print(f"[SequenceWorker] Email record {email_record_id} introuvable")
            continue
        lead_data = dict(zip([col[0] for col in cursor.description], email_row))
        html = build_premium_email(lead_data, verify_link=False)
        # Extraire l'objet depuis le <title>
        import re
        m = re.search(r'<title>([^<]+)</title>', html)
        subject = m.group(1) if m else 'Relance Audit'
        body = html
        to_email = lead_data.get('email')

        # 5. Envoyer l'email via Resend avec retry
        success, msg = sender.send_with_retry(email_record_id, to_email, subject, body)
        if success:
            print(f"[SequenceWorker] Relance envoyée à {to_email} (seq {sequence_id})")
            seq_service.mark_sequence_sent(sequence_id, email_record_id)
        else:
            print(f"[SequenceWorker] Échec envoi relance {sequence_id}: {msg}")

if __name__ == '__main__':
    run_sequence_worker()
