# -*- coding: utf-8 -*-
"""
Module envoi/brevo_sender.py
Envoi d'emails de prospection via l'API transactionnelle Brevo.
Lit BREVO_API_KEY, BREVO_SENDER_EMAIL, BREVO_SENDER_NAME depuis .env
Logs dans errors.log, incrémente brevo_usage dans config_comptes.
"""

import os
import logging
import requests
from typing import Dict, Any, Optional

from dotenv import load_dotenv

# Chargement du .env (dossier parent, c-à-d la racine du projet)
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Logging vers errors.log à la racine du projet
log_path = os.path.join(os.path.dirname(__file__), '..', 'errors.log')
logging.basicConfig(
    filename=log_path,
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# URL de l'API Brevo SMTP
BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def send_prospecting_email(
    prospect_email: str,
    prospect_nom: str,
    email_objet: str,
    email_corps: str,
    lien_rapport: Optional[str] = None,
    dry_run: bool = False,
    compte_id: Optional[str] = None,
    is_html: bool = True
) -> Dict[str, Any]:
    """
    ⚠️  NE PAS UTILISER pour la prospection commerciale.
        L'envoi de prospection se fait via envoi/resend_sender.py → send_prospecting_email().

    Cette fonction est uniquement appelée par send_email() ci-dessous,
    pour les alertes internes (notifications d'ouverture, etc.).

    Args:
        prospect_email  : Adresse email du destinataire
        prospect_nom    : Nom de l'établissement / prospect
        email_objet     : Objet de l'email
        email_corps     : Corps du mail (HTML ou texte brut)
        lien_rapport    : Lien vers le rapport (optionnel)
        dry_run         : Si True, simule l'envoi sans appel API
        compte_id       : ID du compte pour incrémenter usage
        is_html         : Si True (défaut), envoie en tant que htmlContent
    """

    # --- Substitution du lien rapport dans le corps ---
    if lien_rapport and "[lien rapport]" in email_corps:
        email_corps = email_corps.replace("[lien rapport]", lien_rapport)

    # --- Mode dry run : aucun appel API ---
    if dry_run:
        print(f"[DRY RUN BREVO] À : {prospect_email}")
        return {"success": True, "statut": "dry_run", "message_id": "dry_run_id", "erreur": None}

    # --- Lecture des clés depuis .env ---
    brevo_key   = os.getenv("BREVO_API_KEY")
    sender_email = os.getenv("BREVO_SENDER_EMAIL", "jmedansi@incidenx.com")
    sender_name  = os.getenv("BREVO_SENDER_NAME", "Jean-Marc DANSI")

    if not brevo_key:
        msg = "BREVO_API_KEY manquante dans .env"
        logger.error(msg)
        return {"success": False, "statut": "erreur_config", "message_id": None, "erreur": msg}

    # --- Construction du payload Brevo ---
    headers = {
        "accept": "application/json",
        "api-key": brevo_key,
        "content-type": "application/json"
    }
    
    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": prospect_email, "name": prospect_nom}],
        "subject": email_objet
    }
    
    if is_html:
        payload["htmlContent"] = email_corps
    else:
        payload["textContent"] = email_corps

    # --- Envoi ---
    try:
        response = requests.post(BREVO_API_URL, json=payload, headers=headers, timeout=15)
        response.raise_for_status()

        data = response.json()
        message_id = data.get("messageId", "")

        # Incrémenter le compteur brevo_usage dans config_comptes si compte_id fourni
        if compte_id:
            try:
                import sys
                sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
                from config_manager import increment_usage
                increment_usage(compte_id, "brevo")
            except Exception as e:
                logger.error(f"Erreur increment_usage brevo ({compte_id}): {e}")

        return {
            "success": True,
            "statut": "envoye",
            "message_id": message_id,
            "erreur": None
        }

    except requests.exceptions.HTTPError as e:
        msg = f"Erreur HTTP Brevo ({response.status_code}): {response.text}"
        logger.error(f"send_prospecting_email → {msg}")
        return {"success": False, "statut": "erreur_http", "message_id": None, "erreur": msg}

    except requests.exceptions.Timeout:
        msg = "Timeout lors de l'appel Brevo"
        logger.error(f"send_prospecting_email → {msg}")
        return {"success": False, "statut": "erreur_timeout", "message_id": None, "erreur": msg}

    except Exception as e:
        msg = f"Erreur inattendue Brevo: {e}"
        logger.error(f"send_prospecting_email → {msg}")
        return {"success": False, "statut": "erreur_inattendue", "message_id": None, "erreur": msg}

def send_email(to_email: str, subject: str, content: str, is_html: bool = True) -> bool:
    """Version simplifiée pour les alertes internes."""
    res = send_prospecting_email(
        prospect_email=to_email,
        prospect_nom="Admin",
        email_objet=subject,
        email_corps=content,
        is_html=is_html
    )
    return res.get("success", False)

if __name__ == "__main__":
    # Petit test si lancé directement
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
    print("Test envoi simple...")
    # send_email("jmedansi@incidenx.com", "Sujet Test", "Contenu Test")
