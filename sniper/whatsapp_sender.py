# -*- coding: utf-8 -*-
"""
sniper/whatsapp_sender.py — Canal WhatsApp (fallback formulaire)

Flux :
  1. Vérifie que le lead a un numéro mobile FR (06/07)
  2. Ouvre wa.me/{numero} avec un message pré-rempli via Patchright
  3. Clique "Continuer vers le chat" puis envoie le message
  4. Mise à jour DB : statut = 'whatsapp_envoye'
  5. Notification Telegram

Déclenchement :
  Appelé quand email + LinkedIn + formulaire ont tous échoué
  ET que le lead a un numéro de téléphone mobile FR.

Pré-requis :
  - WhatsApp Web connecté dans le profil de navigateur persistant
  - WHATSAPP_PROFILE_PATH dans .env (chemin vers le profil Chrome avec WA Web)
    ex: WHATSAPP_PROFILE_PATH=C:/Users/jmeda/AppData/Local/WhatsApp-Profile
"""

import logging
import os
import random
import re
import sys
import time
from typing import Optional
from urllib.parse import quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

logger = logging.getLogger(__name__)

_MESSAGE_TEMPLATE = (
    "Bonjour{prenom_part},\n\n"
    "Je me permets de vous contacter au sujet de votre site {site}.\n\n"
    "J'ai réalisé un audit gratuit et identifié des points concrets "
    "qui impactent votre visibilité sur Google et vos performances mobiles.\n\n"
    "Seriez-vous disponible pour en discuter quelques minutes ?\n\n"
    "Bien cordialement,\n{sender_name}"
)

_MOBILE_RE = re.compile(r"^(?:\+33|0033|0)[67]\d{8}$")


def _normalize_phone(phone: str) -> Optional[str]:
    """
    Normalise un numéro FR vers le format international sans + ni espaces.
    Ex: 06 12 34 56 78 → 33612345678
    Retourne None si le numéro n'est pas un mobile FR valide.
    """
    if not phone:
        return None
    clean = re.sub(r"[\s.\-()]", "", phone)
    if clean.startswith("+33"):
        clean = "33" + clean[3:]
    elif clean.startswith("0033"):
        clean = "33" + clean[4:]
    elif clean.startswith("0"):
        clean = "33" + clean[1:]

    # Vérifier mobile FR (06/07)
    if re.match(r"^336\d{8}$", clean) or re.match(r"^337\d{8}$", clean):
        return clean

    return None


def _human_delay(min_s: float = 0.5, max_s: float = 1.5):
    time.sleep(random.uniform(min_s, max_s))


def send_whatsapp_outreach(
    lead_id:  int,
    phone:    str,
    site_web: str = "",
    prenom:   str = "",
    nom:      str = "",
) -> bool:
    """
    Envoie un message WhatsApp via WhatsApp Web.

    Args:
        lead_id:  ID du lead en base
        phone:    Numéro de téléphone du lead
        site_web: URL du site (pour le message)
        prenom:   Prénom du dirigeant (optionnel)
        nom:      Nom du dirigeant (optionnel)
        headless: False recommandé (WhatsApp détecte les browsers headless)

    Returns:
        True si message envoyé, False sinon.
    """
    number = _normalize_phone(phone)
    if not number:
        logger.info(f"whatsapp_sender: numéro non mobile FR pour lead {lead_id}: {phone}")
        return False

    from core.config import ensure_env
    ensure_env()

    sender_name = os.getenv("SENDER_NAME") or os.getenv("BREVO_SENDER_NAME", "Jean-Marc DANSI")
    from urllib.parse import urlparse
    domain        = urlparse(site_web).netloc.lstrip("www.") if site_web else number

    prenom_part = f" {prenom}" if prenom else ""
    message = _MESSAGE_TEMPLATE.format(
        prenom_part = prenom_part,
        site        = domain or phone,
        sender_name = sender_name,
    )

    wa_url = f"https://web.whatsapp.com/send?phone={number}&text={quote(message)}"

    from core.browser import cdp_tab

    try:
        with cdp_tab(viewport={"width": 1280, "height": 800}) as page:
            page.goto(wa_url, wait_until="domcontentloaded", timeout=30000)
            _human_delay(4, 6)

            qr = page.locator("canvas[aria-label*='QR'], [data-testid='qrcode']")
            if qr.count() > 0:
                logger.warning("whatsapp_sender: WhatsApp Web non connecté — QR code affiché")
                return False

            try:
                page.wait_for_selector(
                    "[data-testid='conversation-compose-box-input'], "
                    "div[contenteditable='true'][data-tab]",
                    timeout=15000
                )
            except Exception:
                logger.warning(f"whatsapp_sender: zone de saisie introuvable pour {number}")
                return False

            _human_delay(1, 2)

            send_btn = None
            for sel in [
                "[data-testid='send'], [data-testid='send-button']",
                "button[aria-label='Envoyer']", "button[aria-label='Send']",
                "span[data-icon='send']",
            ]:
                loc = page.locator(sel).first
                try:
                    if loc.count() > 0 and loc.is_visible():
                        send_btn = loc
                        break
                except Exception:
                    continue

            if not send_btn:
                page.locator(
                    "[data-testid='conversation-compose-box-input'], "
                    "div[contenteditable='true'][data-tab]"
                ).first.press("Enter")
                logger.info(f"whatsapp_sender: message envoyé via Enter → {number}")
            else:
                send_btn.click()
                logger.info(f"whatsapp_sender: message envoyé → {number}")

            _human_delay(1, 2)

        _update_db(lead_id)
        _notify_telegram(prenom, nom, domain, number)
        return True

    except Exception as e:
        logger.error(f"whatsapp_sender: erreur pour {number} — {e}")
        return False


def _update_db(lead_id: int):
    try:
        from database.connection import get_conn
        with get_conn() as conn:
            conn.execute(
                "UPDATE leads_bruts SET statut='whatsapp_envoye' WHERE id=?",
                (lead_id,)
            )
            conn.execute(
                "UPDATE leads_audites SET statut_prospection='whatsapp_envoye' WHERE lead_id=?",
                (lead_id,)
            )
            conn.commit()
    except Exception as e:
        logger.warning(f"whatsapp_sender: DB update échouée — {e}")


def _notify_telegram(prenom: str, nom: str, domain: str, number: str):
    try:
        from core.telegram_adapter import notify
        contact = f"{prenom} {nom}".strip() or domain
        notify(
            f"WhatsApp — {contact}",
            f"*WhatsApp envoyé*\n"
            f"Contact : {contact}\n"
            f"Domaine : {domain}\n"
            f"Numéro : +{number}\n\n"
            f"_Email/LinkedIn/formulaire impossibles — canal WhatsApp activé_",
        )
    except Exception as e:
        logger.debug(f"whatsapp_sender: Telegram échoué — {e}")
