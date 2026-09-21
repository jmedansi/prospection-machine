# -*- coding: utf-8 -*-
"""
services/smtp_email_sender_service.py
Service d'envoi d'emails de prospection via SMTP direct.
"""
import threading
from database import (
    get_audits_ready_for_email,
    insert_email_sent,
    logger,
)

from envoi.smtp_sender import send_prospecting_email_smtp
from .job_tracker import _email_job, reset_email_job


def send_approved_emails_smtp(lead_ids=None):
    """
    Envoie tous les emails approuvés via SMTP direct.
    """
    if _email_job['running']:
        return False, 'Un envoi est déjà en cours'

    candidats = get_audits_ready_for_email()

    filtered = []
    for lead in candidats:
        lid_str = str(lead.get('lead_id'))
        if lead_ids and lid_str not in [str(x) for x in lead_ids]:
            continue
        if not lead.get('approuve'):
            continue
        filtered.append(lead)

    if not filtered:
        return False, 'Aucun email approuvé à envoyer'

    reset_email_job(total=len(filtered))

    def _run():
        try:
            for lead in filtered:
                _email_job['current'] += 1
                nom = lead.get('nom', 'prospect')
                email = lead.get('email', '').strip()
                email_objet = lead.get('email_objet', '').strip()
                email_corps = lead.get('email_corps', '').strip()
                lien = lead.get('lien_rapport', '').strip() or lead.get('site_web') or 'https://audit.incidenx.com'

                if not email or not email_corps:
                    _email_job['failed'] += 1
                    _email_job['results'].append({'nom': nom, 'statut': 'skip', 'raison': 'Email ou corps manquant'})
                    continue

                result = send_prospecting_email_smtp(
                    prospect_email=email,
                    prospect_nom=nom,
                    email_objet=email_objet,
                    email_corps=email_corps,
                    lien_rapport=lien,
                    dry_run=False,
                )

                if result.get('success'):
                    email_record_id = insert_email_sent({
                        'lead_id': lead.get('lead_id'),
                        'message_id_resend': '',
                        'email_objet': email_objet,
                        'email_corps': email_corps,
                        'email_destinataire': email,
                        'lien_rapport': lien,
                        'statut_envoi': 'envoye',
                    })
                    _email_job['success'] += 1
                    _email_job['results'].append({'nom': nom, 'statut': 'ok'})
                else:
                    _email_job['failed'] += 1
                    _email_job['results'].append({'nom': nom, 'statut': 'error', 'raison': result.get('erreur')})
        except Exception as e:
            logger.error(f'Erreur services/smtp_email_sender_service: {e}')
        finally:
            _email_job['running'] = False

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return True, f'Envoi SMTP de {len(filtered)} emails lancé'
