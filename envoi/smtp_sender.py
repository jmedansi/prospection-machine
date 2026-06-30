# -*- coding: utf-8 -*-
"""
Module envoi/smtp_sender.py
Envoi d'emails de prospection via SMTP direct depuis une boîte mail.
Lit SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
SMTP_USE_SSL, SMTP_USE_TLS, SMTP_FROM_EMAIL, SMTP_FROM_NAME depuis .env.
"""

import os
import logging
import smtplib
import re
from typing import Dict, Any, Optional, List
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from core.config import ensure_env

ensure_env()

# Logging vers errors.log à la racine du projet
log_path = os.path.join(os.path.dirname(__file__), '..', 'errors.log')
logging.basicConfig(
    filename=log_path,
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def _bool_env(key: str, default: bool = False) -> bool:
    value = os.getenv(key, None)
    if value is None:
        return default
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def _strip_html(html: str) -> str:
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _build_message(
    from_name: str,
    from_email: str,
    to_emails: List[str],
    subject: str,
    body: str,
    reply_to: Optional[str] = None,
) -> MIMEMultipart:
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject or ''
    msg['From'] = formataddr((from_name, from_email)) if from_name else from_email
    msg['To'] = ', '.join(to_emails)
    if reply_to:
        msg['Reply-To'] = reply_to

    if body.strip().startswith('<') or '<html' in body.lower():
        plain = _strip_html(body)
        text_part = MIMEText(plain or body, 'plain', 'utf-8')
        html_part = MIMEText(body, 'html', 'utf-8')
        msg.attach(text_part)
        msg.attach(html_part)
    else:
        text_part = MIMEText(body, 'plain', 'utf-8')
        msg.attach(text_part)

    return msg


def send_prospecting_email_smtp(
    prospect_email: str,
    prospect_nom: str,
    email_objet: str,
    email_corps: str,
    lien_rapport: Optional[str] = None,
    dry_run: bool = False,
    reply_to: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Envoie un email de prospection via SMTP.

    Args:
        prospect_email: adresse destinataire ou liste séparée par des virgules
        prospect_nom:  nom du prospect (utilisé uniquement pour logging)
        email_objet:    objet du message
        email_corps:    corps HTML ou texte
        lien_rapport:   lien facultatif à remplacer dans le corps
        dry_run:        si True, ne fait pas d'envoi réel
        reply_to:       adresse Reply-To si nécessaire

    Retourne:
        Dict avec les clés success, statut, message_id, erreur
    """
    if lien_rapport and '[lien rapport]' in email_corps:
        email_corps = email_corps.replace('[lien rapport]', lien_rapport)

    to_emails = [e.strip() for e in prospect_email.split(',') if e.strip()]

    if dry_run:
        print(f"[DRY RUN SMTP] À : {to_emails}")
        print(f"[DRY RUN SMTP] Objet : {email_objet}")
        return {
            'success': True,
            'statut': 'dry_run',
            'message_id': None,
            'erreur': None,
        }

    smtp_host = os.getenv('SMTP_HOST', '').strip()
    if not smtp_host:
        # Fallback sur la configuration IMAP
        smtp_host = os.getenv('IMAP_HOST', '').strip()
        
    smtp_port = int(os.getenv('SMTP_PORT', '465').strip() or 465)
    
    smtp_user = os.getenv('SMTP_USER', '').strip()
    if not smtp_user:
        smtp_user = os.getenv('IMAP_USER', '').strip()
        
    smtp_password = os.getenv('SMTP_PASSWORD', '').strip()
    if not smtp_password:
        smtp_password = os.getenv('IMAP_PASSWORD', '').strip()
        
    smtp_use_ssl = _bool_env('SMTP_USE_SSL', True)
    smtp_use_tls = _bool_env('SMTP_USE_TLS', False)
    
    from_email = os.getenv('SMTP_FROM_EMAIL', '').strip()
    if not from_email:
        from_email = smtp_user
        
    from_name = os.getenv('SMTP_FROM_NAME', '').strip()
    if not from_name:
        from_name = os.getenv('BREVO_SENDER_NAME', 'Jean-Marc DANSI').strip()

    if not smtp_host:
        msg = 'SMTP_HOST manquant dans .env'
        logger.error(msg)
        return {'success': False, 'statut': 'erreur_config', 'message_id': None, 'erreur': msg}

    if not from_email:
        msg = 'SMTP_FROM_EMAIL ou SMTP_USER manquant dans .env'
        logger.error(msg)
        return {'success': False, 'statut': 'erreur_config', 'message_id': None, 'erreur': msg}

    if not to_emails:
        msg = 'Aucun destinataire SMTP fourni'
        logger.error(msg)
        return {'success': False, 'statut': 'erreur_config', 'message_id': None, 'erreur': msg}

    message = _build_message(from_name, from_email, to_emails, email_objet, email_corps, reply_to)

    try:
        if smtp_use_ssl:
            smtp = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=20)
        else:
            smtp = smtplib.SMTP(smtp_host, smtp_port, timeout=20)

        smtp.ehlo()

        if smtp_use_tls and not smtp_use_ssl:
            smtp.starttls()
            smtp.ehlo()

        if smtp_user and smtp_password:
            smtp.login(smtp_user, smtp_password)

        smtp.sendmail(from_email, to_emails, message.as_string())
        smtp.quit()

        return {
            'success': True,
            'statut': 'envoye',
            'message_id': None,
            'erreur': None,
        }

    except Exception as e:
        msg = f'Erreur envoi SMTP: {e}'
        logger.error(msg)
        return {
            'success': False,
            'statut': 'erreur_inattendue',
            'message_id': None,
            'erreur': msg,
        }
