# -*- coding: utf-8 -*-
"""
services/email_sequence_service.py
Gestion des sequences de relances email.

Flux :
  1. plan_sequences_for_lead() : planifie 3 relances (J+3, J+7, J+14)
  2. generate_and_request_approval() : genere le contenu + demande validation Telegram
  3. send_approved_sequence() : envoie l'email + marque 'sent' (appele par le poller)
"""

import json
import logging
import os
import re
from datetime import datetime, timedelta
from database.connection import get_conn

logger = logging.getLogger(__name__)


class EmailSequenceService:
    """Gerer les sequences de relances avec validation Telegram."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path

    def plan_sequences_for_lead(self, lead_id: int, initial_email_record_id: int):
        with get_conn() as conn:
            row = conn.execute(
                "SELECT date_envoi FROM emails_envoyes WHERE id=?",
                (initial_email_record_id,)
            ).fetchone()
            if not row or not row[0]:
                return

            initial_send_date = datetime.fromisoformat(row[0])
            now = datetime.now().isoformat()
            sequences = [
                ('relance_1',       3,  json.dumps({'nb_clics': 0})),
                ('relance_2',       7,  json.dumps({'nb_clics': 0, 'date_ouverture': True})),
                ('relance_special', 14, json.dumps({'lead_temperature': ['chaud', 'tiede']})),
            ]
            for email_type, days, condition in sequences:
                date_planifiee = (initial_send_date + timedelta(days=days)).isoformat()
                conn.execute("""
                    INSERT INTO email_sequences
                    (lead_id, email_record_id, email_type, statut, date_planifiee,
                     condition_envoi, created_at)
                    VALUES (?, ?, ?, 'planned', ?, ?, ?)
                """, (lead_id, initial_email_record_id, email_type,
                      date_planifiee, condition, now))
            conn.commit()

    def get_sequences_to_process(self) -> list:
        """Sequences planifiees et arrivees a echeance."""
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT seq.*, ee.lead_id, ee.email_destinataire AS email,
                       ee.score_lead, ee.lead_temperature, ee.repondu, ee.clique
                FROM email_sequences seq
                JOIN emails_envoyes ee ON seq.email_record_id = ee.id
                WHERE seq.statut = 'planned' AND seq.date_planifiee <= ?
                ORDER BY seq.date_planifiee ASC
            """, (datetime.now().isoformat(),)).fetchall()
        return [dict(row) for row in rows]

    def get_sequences_pending_approval(self) -> list:
        """Sequences en attente d'approval Telegram."""
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT seq.*, ee.email_destinataire AS email
                FROM email_sequences seq
                JOIN emails_envoyes ee ON seq.email_record_id = ee.id
                WHERE seq.statut = 'pending_approval'
                ORDER BY seq.date_planifiee ASC
            """).fetchall()
        return [dict(row) for row in rows]

    def should_send_sequence(self, sequence: dict) -> bool:
        if sequence.get('repondu') or sequence.get('clique'):
            return False

        condition_str = sequence.get('condition_envoi')
        if not condition_str:
            return True
        try:
            condition = json.loads(condition_str)
        except Exception:
            return True

        if 'nb_clics' in condition:
            with get_conn() as conn:
                row = conn.execute(
                    "SELECT nb_clics FROM emails_envoyes WHERE lead_id=?",
                    (sequence['lead_id'],)
                ).fetchone()
            if row and row[0] >= condition['nb_clics']:
                return False
        return True

    def generate_and_request_approval(self, sequence: dict) -> bool:
        """
        Genere le contenu de la relance et envoie une demande de validation Telegram.
        Retourne True si la demande a ete envoyee, False sinon.
        """
        lead_id = sequence['lead_id']
        sequence_id = sequence['id']
        email_record_id = sequence['email_record_id']
        email_type = sequence['email_type']

        # 1. Recuperer les infos du lead
        with get_conn() as conn:
            lead_row = conn.execute(
                "SELECT * FROM leads_audites WHERE id=?", (lead_id,)
            ).fetchone()
            email_row = conn.execute(
                "SELECT * FROM emails_envoyes WHERE id=?", (email_record_id,)
            ).fetchone()

        if not lead_row or not email_row:
            logger.warning(f"[Sequence] Lead {lead_id} ou email {email_record_id} introuvable")
            return False

        lead_data = dict(lead_row)
        email_data = dict(email_row)

        # 2. Generer l'email avec email_builder
        try:
            from envoi.email_builder import build_premium_email
            html = build_premium_email(lead_data, verify_link=False)
            m = re.search(r'<title>([^<]+)</title>', html)
            subject = m.group(1) if m else f"Relance {email_type} - {lead_data.get('nom_societe', '')}"
            body = html
        except Exception as e:
            logger.error(f"[Sequence] Erreur generation email: {e}")
            return False

        # 3. Stocker le contenu et passer en pending_approval
        with get_conn() as conn:
            conn.execute(
                "UPDATE email_sequences SET statut='pending_approval', email_objet=?, email_corps=? WHERE id=?",
                (subject, body, sequence_id)
            )
            conn.commit()

        # 4. Envoyer la demande de validation Telegram
        to_email = email_data.get('email_destinataire', '?')
        nom = lead_data.get('nom_societe', lead_data.get('company_name', ''))
        preview = (
            f"*Relance {email_type}*\n"
            f"Societe: {nom}\n"
            f"Contact: {to_email}\n"
            f"Objet: {subject}\n\n"
            f"{'─'*30}\n"
            f"{self._strip_html(body)[:300]}..."
        )
        callback_id = f"relance_approve_{sequence_id}"

        try:
            from core.telegram_adapter import send_validation_request
            result = send_validation_request(
                outil=f"sequence_{sequence_id}",
                preview=preview,
                callback_id=callback_id,
                timeout_minutes=2880,
            )
            logger.info(f"[Sequence] Validation request sent for seq {sequence_id}: {result}")
            return True
        except Exception as e:
            logger.error(f"[Sequence] Erreur envoi Telegram: {e}")
            # On annule pas le pending_approval, ca sera retente
            return True

    def approve_and_send(self, sequence_id: int) -> bool:
        """
        Envoie l'email de relance approuve et marque la sequence terminee.
        Appele par le poller Telegram.
        """
        from services.lead_scoring_service import LeadScoringService
        from envoi.resend_sender_with_retry import ResendSenderWithRetry

        with get_conn() as conn:
            seq = conn.execute(
                "SELECT * FROM email_sequences WHERE id=?", (sequence_id,)
            ).fetchone()

        if not seq:
            logger.warning(f"[Sequence] Sequence {sequence_id} introuvable")
            return False

        if seq['statut'] != 'pending_approval':
            logger.info(f"[Sequence] Sequence {sequence_id} deja traitee (statut={seq['statut']})")
            return False

        # Mise a jour score avant envoi
        try:
            LeadScoringService().update_lead_score(seq['lead_id'])
        except Exception as e:
            logger.debug(f"[Sequence] Score update failed: {e}")

        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'data', 'prospection.db'
        )
        sender = ResendSenderWithRetry(
            os.environ.get('RESEND_API_KEY', 'changeme'), db_path
        )

        # Recuperer l'email depuis le record d'envoi original
        to_email = self._get_email_from_record(seq['email_record_id']) or self._get_email(seq['lead_id'])
        subject = seq['email_objet'] or 'Relance Audit'
        body = seq['email_corps'] or ''

        success, msg = sender.send_with_retry(
            seq['email_record_id'], to_email, subject, body
        )

        if success:
            with get_conn() as conn:
                conn.execute(
                    "UPDATE email_sequences SET statut='sent', date_envoi=? WHERE id=?",
                    (datetime.now().isoformat(), sequence_id)
                )
                conn.commit()
            logger.info(f"[Sequence] Relance envoyee pour seq {sequence_id}")
            return True
        else:
            logger.error(f"[Sequence] Echec envoi seq {sequence_id}: {msg}")
            return False

    def _get_email_from_record(self, email_record_id: int) -> str:
        try:
            with get_conn() as conn:
                r = conn.execute(
                    "SELECT email_destinataire FROM emails_envoyes WHERE id=?",
                    (email_record_id,)
                ).fetchone()
                return r[0] if r else ''
        except Exception:
            return ''

    def _get_email(self, lead_id: int) -> str:
        try:
            with get_conn() as conn:
                r = conn.execute(
                    "SELECT email_valide FROM leads_audites WHERE id=?", (lead_id,)
                ).fetchone()
                return r[0] if r else ''
        except Exception:
            return ''

    def _strip_html(self, html: str) -> str:
        clean = re.sub(r'<[^>]+>', ' ', html)
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean[:500]

    def cancel_lead_sequences(self, lead_id: int):
        """Annule toutes les sequences planifiees pour un lead (si reponse recue)."""
        with get_conn() as conn:
            conn.execute(
                "UPDATE email_sequences SET statut='cancelled' WHERE lead_id=? AND statut='planned'",
                (lead_id,)
            )
            conn.commit()
