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
        """Sequences planifiees et arrivees a echeance. Exclut les leads sans site_web."""
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT seq.*, ee.lead_id, ee.email_destinataire AS email,
                       ee.score_lead, ee.lead_temperature, ee.repondu, ee.clique
                FROM email_sequences seq
                JOIN emails_envoyes ee ON seq.email_record_id = ee.id
                JOIN leads_bruts lb ON lb.id = ee.lead_id
                WHERE seq.statut = 'planned' AND seq.date_planifiee <= ?
                  AND (lb.site_web IS NOT NULL AND lb.site_web != '')
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

    def generate_and_request_approval(self, sequence: dict, send_telegram: bool = True) -> bool:
        """
        Genere le contenu de la relance et passe en pending_approval.
        Si send_telegram=True, envoie une demande de validation individuelle.
        Retourne True en cas de succes.
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

        # 2. Generer l'email en utilisant les mails de sequence directement
        try:
            from envoi.sequence_emails import get_mail_1, MAIL_2_J3, MAIL_3_J7, MAIL_4_J14
            
            # Recuperer secteur depuis leads_bruts
            secteur = ''
            with get_conn() as conn:
                br = conn.execute(
                    "SELECT secteur, category FROM leads_bruts WHERE id=?",
                    (lead_data.get('lead_id'),)
                ).fetchone()
                if br:
                    secteur = (br['secteur'] or br['category'] or '')
            
            # Choisir le mail selon email_type
            if email_type == 'relance_1':
                mail = MAIL_2_J3
            elif email_type == 'relance_2':
                mail = MAIL_3_J7
            elif email_type == 'relance_special':
                mail = MAIL_4_J14
            else:
                logger.warning(f"[Sequence] email_type inconnu: {email_type}")
                return False
            
            subject = mail.get('subject', 'Relance')
            body = mail.get('body', '')
            
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

        # 4. Envoyer la demande de validation Telegram (si demande)
        if not send_telegram:
            return True

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

    def request_bulk_approval(self, count: int) -> bool:
        """Envoie un recapitulatif Telegram pour valider toutes les relances d'un coup."""
        preview = (
            f"🚀 *{count} relances prêtes !*\n\n"
            f"Le contenu a été généré.\n"
            f"Souhaitez-vous toutes les envoyer ?"
        )
        try:
            from core.telegram_adapter import send_validation_request
            result = send_validation_request(
                outil=f"sequences_bulk",
                preview=preview,
                callback_id="relance_approve_all",
                timeout_minutes=2880,
            )
            logger.info(f"[Sequence] Bulk validation request sent for {count} seqs")
            return True
        except Exception as e:
            logger.error(f"[Sequence] Erreur envoi bulk Telegram: {e}")
            return False

    def approve_all_pending(self) -> int:
        """
        Envoie toutes les séquences en attente d'approbation.
        Retourne le nombre de séquences envoyées.
        """
        pending = self.get_sequences_pending_approval()
        count = 0
        for seq in pending:
            if self.approve_and_send(seq['id']):
                count += 1
        return count

    def approve_and_send(self, sequence_id: int) -> bool:
        """
        Envoie l'email de relance approuve et marque la sequence terminee.
        Appele par le poller Telegram.
        """
        from services.lead_scoring_service import LeadScoringService
        from envoi.resend_sender_with_retry import ResendSenderWithRetry
        from envoi.smtp_sender import send_prospecting_email_smtp

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

        # Recuperer les donnees du lead et l'email
        with get_conn() as conn:
            lead = conn.execute(
                "SELECT * FROM leads_audites WHERE id=?", (seq['lead_id'],)
            ).fetchone()
        
        lead_data = dict(lead) if lead else {}
        to_email = self._get_email_from_record(seq['email_record_id']) or self._get_email(seq['lead_id'])
        subject = seq['email_objet'] or 'Relance'
        body = seq['email_corps'] or ''

        # Utiliser SMTP par défaut, sauf si DISABLE_SMTP_SEND est à 1
        use_smtp = os.environ.get('DISABLE_SMTP_SEND', '0').strip() != '1'
        try:
            if use_smtp:
                result = send_prospecting_email_smtp(
                    prospect_email=to_email,
                    prospect_nom=lead_data.get('nom_societe', lead_data.get('nom', '')),
                    email_objet=subject,
                    email_corps=body,
                    lien_rapport=lead_data.get('lien_rapport'),
                    dry_run=False,
                )
                success = bool(result.get('success'))
                msg_id = result.get('message_id')
                msg = result.get('erreur')
            else:
                import requests as _req
                api_key = os.environ.get('RESEND_API_KEY', 'changeme')
                from_email = os.environ.get('RESEND_FROM_EMAIL', os.environ.get('RESEND_SENDER_EMAIL', 'jmedansi@incidenx.com'))
                sender_name = os.environ.get('RESEND_SENDER_NAME', 'Jean-Marc DANSI')
                
                from_payload = f"{sender_name} <onboarding@resend.dev>" if "resend.dev" in from_email else f"{sender_name} <{from_email}>"
                
                resp = _req.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"from": from_payload, "to": [to_email], "subject": subject, "html": body.replace('\n', '<br>')},
                    timeout=15,
                )
                if resp.status_code in (200, 201):
                    success = True
                    msg_id = resp.json().get('id', '')
                    msg = None
                else:
                    success = False
                    msg_id = None
                    msg = resp.text[:200]

            if success:
                now = datetime.now().isoformat()

                # ── 1. Marquer la séquence comme envoyée ──────────────────────
                with get_conn() as conn:
                    conn.execute(
                        "UPDATE email_sequences SET statut='sent', date_envoi=? WHERE id=?",
                        (now, sequence_id)
                    )

                    # ── 2. Insérer dans emails_envoyes pour le CRM ────────────
                    # Récupérer lead_id (leads_bruts) depuis leads_audites
                    lb_row = conn.execute(
                        "SELECT lead_id FROM leads_audites WHERE id=?", (seq['lead_id'],)
                    ).fetchone()
                    lb_id = lb_row['lead_id'] if lb_row else None

                    followup_record_id = None
                    if lb_id:
                        cur = conn.execute("""
                            INSERT INTO emails_envoyes
                                (lead_id, email_destinataire, email_objet, email_corps,
                                 statut_envoi, message_id_resend, date_envoi)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (lb_id, to_email, subject, body, seq['email_type'], msg_id or '', now))
                        followup_record_id = cur.lastrowid

                    conn.commit()

                # ── 3. Planifier la prochaine étape de relance ────────────────
                NEXT_STEP = {
                    'relance_1':       ('relance_2',       4),   # +4 jours → J+7 total
                    'relance_2':       ('relance_special', 7),   # +7 jours → J+14 total
                    'relance_special': (None, 0),                # fin de séquence
                }
                email_type = dict(seq)['email_type']
                next_type, next_days = NEXT_STEP.get(email_type, (None, 0))

                if next_type and followup_record_id:
                    date_next = (datetime.now() + timedelta(days=next_days)).isoformat()
                    condition = json.dumps({'nb_clics': 0})
                    with get_conn() as conn:
                        conn.execute("""
                            INSERT INTO email_sequences
                                (lead_id, email_record_id, email_type, statut,
                                 date_planifiee, condition_envoi, created_at)
                            VALUES (?, ?, ?, 'planned', ?, ?, ?)
                        """, (seq['lead_id'], followup_record_id, next_type,
                              date_next, condition, now))
                        conn.commit()
                    logger.info(
                        f"[Sequence] Prochaine etape planifiee : {next_type} "
                        f"dans {next_days}j pour lead {seq['lead_id']}"
                    )

                logger.info(f"[Sequence] Relance {email_type} envoyee (seq {sequence_id})")
                return True
            else:
                logger.error(f"[Sequence] Echec envoi seq {sequence_id}: {msg}")
                return False
        except Exception as e:
            logger.error(f"[Sequence] Exception envoi seq {sequence_id}: {e}")
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
        """Annule toutes les sequences planifiees ou en attente d'approbation pour un lead."""
        with get_conn() as conn:
            conn.execute(
                "UPDATE email_sequences SET statut='cancelled' WHERE lead_id=? AND statut IN ('planned', 'pending_approval')",
                (lead_id,)
            )
            conn.commit()
