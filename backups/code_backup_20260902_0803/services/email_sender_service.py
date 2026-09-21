# -*- coding: utf-8 -*-
"""
services/email_sender_service.py
Gère l'envoi de batches d'emails via Resend.
"""
import os
import threading
from database import (
    get_conn, get_audits_ready_for_email, insert_email_sent, logger
)
from .job_tracker import _email_job, reset_email_job

def send_approved_emails(lead_ids=None):
    """
    Envoie tous les emails approuvés (ou une liste spécifique) via Resend.
    """
    if _email_job['running']:
        return False, "Un envoi est déjà en cours"

    from envoi.resend_sender import send_prospecting_email
    candidats = get_audits_ready_for_email()

    # Filtrer les leads à envoyer
    filtered = []
    for lead in candidats:
        lid_str = str(lead.get('lead_id'))
        if lead_ids and lid_str not in [str(x) for x in lead_ids]:
            continue
        if not lead.get('approuve'):
            continue
        filtered.append(lead)

    if not filtered:
        return False, "Aucun email approuvé à envoyer"

    reset_email_job(total=len(filtered))

    def _run():
        try:
            for lead in filtered:
                _email_job['current'] += 1
                nom = lead.get('nom', 'prospect')
                email = lead.get('email', '').strip()
                email_objet = lead.get('email_objet', '').strip()
                email_corps = lead.get('email_corps', '').strip()
                lien = lead.get('lien_rapport', '').strip() or lead.get('site_web') or "https://audit.incidenx.com"

                if not email or not email_corps:
                    _email_job['failed'] += 1
                    _email_job['results'].append({'nom': nom, 'statut': 'skip', 'raison': 'Email ou corps manquant'})
                    continue

                # Ajout du wrapper HTML si nécessaire (le builder génère déjà de l'HTML complet par défaut)
                html_premium = email_corps
                if not email_corps.strip().startswith('<'):
                    html_premium = f"<!DOCTYPE html><html><body>{email_corps.replace('\n', '<br>')}</body></html>"

                result = send_prospecting_email(
                    prospect_email=email,
                    prospect_nom=nom,
                    email_objet=email_objet,
                    email_corps=html_premium,
                    lien_rapport=lien,
                    dry_run=False
                )

                if result.get('success'):
                    email_record_id = insert_email_sent({
                        'lead_id': lead.get('lead_id'),
                        'message_id_resend': result.get('message_id', ''),
                        'email_objet': email_objet,
                        'email_corps': html_premium,
                        'email_destinataire': email,
                        'lien_rapport': lien,
                        'statut_envoi': 'envoye',
                    })
                    from services.email_sequence_service import EmailSequenceService
                    seq_service = EmailSequenceService('data/prospection.db')
                    seq_service.plan_sequences_for_lead(lead.get('lead_id'), email_record_id)
                    _email_job['success'] += 1
                    _email_job['results'].append({'nom': nom, 'statut': 'ok'})
                else:
                    _email_job['failed'] += 1
                    _email_job['results'].append({'nom': nom, 'statut': 'error', 'raison': result.get('erreur')})
        except Exception as e:
            logger.error(f"Erreur services/email_sender_service: {e}")
        finally:
            _email_job['running'] = False

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return True, f"Envoi de {len(filtered)} emails lancé"
