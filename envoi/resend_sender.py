# -*- coding: utf-8 -*-
"""
Module envoi/resend_sender.py
Envoi d'emails de prospection via l'API Resend.
Lit RESEND_API_KEY, BREVO_SENDER_EMAIL, BREVO_SENDER_NAME depuis .env
Logs dans errors.log.
"""

import os
import logging
import requests
from typing import Dict, Any, Optional

from dotenv import load_dotenv

# Chargement du .env (dossier parent)
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Logging vers errors.log à la racine du projet
log_path = os.path.join(os.path.dirname(__file__), '..', 'errors.log')
logging.basicConfig(
    filename=log_path,
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# URL de l'API Resend
RESEND_API_URL = "https://api.resend.com/emails"


def send_prospecting_email(
    prospect_email: str,
    prospect_nom: str,
    email_objet: str,
    email_corps: str,
    lien_rapport: Optional[str] = None,
    dry_run: bool = False,
    compte_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Envoie un email de prospection via Resend.

    Args:
        prospect_email  : Adresse email du destinataire
        prospect_nom    : Nom de l'établissement / prospect
        email_objet     : Objet de l'email
        email_corps     : Corps du mail
        lien_rapport    : Lien vers le rapport PDF (optionnel)
        dry_run         : Si True, simule l'envoi
        compte_id       : Pour compatibilité (non utilisé pour Resend pour l'instant)

    Returns:
        Dict avec clés : success (bool), statut (str), message_id (str|None), erreur (str|None)
    """

    # --- Substitution du lien rapport ---
    if lien_rapport and "[lien rapport]" in email_corps:
        email_corps = email_corps.replace("[lien rapport]", lien_rapport)

    # --- Mode dry run ---
    if dry_run:
        print(f"[DRY RUN RESEND] À : {prospect_email}")
        print(f"[DRY RUN RESEND] Objet : {email_objet}")
        return {
            "success": True,
            "statut": "dry_run",
            "message_id": None,
            "erreur": None
        }

    # --- Lecture des clés ---
    # On récupère via config_manager pour respecter la règle "jamais en dur"
    try:
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from config_manager import get_config
        config = get_config()
        resend_key = config.get("resend_key")
        sender_email = os.getenv("BREVO_SENDER_EMAIL", "jmedansi@incidenx.com")
        sender_name  = os.getenv("BREVO_SENDER_NAME", "Jean-Marc DANSI")
    except Exception as e:
        msg = f"Erreur chargement config : {e}"
        logger.error(msg)
        return {"success": False, "statut": "erreur_config", "message_id": None, "erreur": msg}

    if not resend_key:
        msg = "RESEND_API_KEY manquante dans config_manager / .env"
        logger.error(msg)
        return {"success": False, "statut": "erreur_config", "message_id": None, "erreur": msg}

    # --- Payload Resend ---
    headers = {
        "Authorization": f"Bearer {resend_key}",
        "Content-Type": "application/json"
    }
    
    # Resend préfère HTML
    # Si le corps contient déjà de l'HTML (via email_builder), on l'utilise tel quel
    if email_corps.strip().startswith("<!DOCTYPE html>") or "<html" in email_corps.lower():
        html_content = email_corps
    else:
        html_content = email_corps.replace("\n", "<br>")
    
    payload = {
        "from": f"{sender_name} <onboarding@resend.dev>" if "resend.dev" in sender_email else f"{sender_name} <{sender_email}>",
        "to": [prospect_email],
        "subject": email_objet,
        "html": html_content
    }

    # Note: Si le domaine n'est pas vérifié sur Resend, il faut utiliser "onboarding@resend.dev"
    # L'utilisateur a probablement configuré son domaine, mais par sécurité je garde un fallback
    # si le sender_email n'est pas encore prêt.
    
    # --- Envoi ---
    try:
        response = requests.post(RESEND_API_URL, json=payload, headers=headers, timeout=15)
        response.raise_for_status()

        data = response.json()
        message_id = data.get("id", "")

        return {
            "success": True,
            "statut": "envoye",
            "message_id": message_id,
            "erreur": None
        }

    except Exception as e:
        msg = f"Erreur envoi Resend: {e}"
        if 'response' in locals():
            msg += f" | {response.text}"
        logger.error(f"send_prospecting_email → {msg}")
        return {"success": False, "statut": "erreur_inattendue", "message_id": None, "erreur": msg}
