# -*- coding: utf-8 -*-
"""
envoi/sequence_emails.py — STUB DÉPRÉCIÉ (purge V1 définitive, 2026-09-24)

⚠️ MODULE VIDÉ DE SON CONTENU. Les mails de séquence codés en dur
("Mail 1 Jour J par secteur", J+3, J+7, J+14) ne sont PLUS une source de
vérité. Tout contenu envoyé provient désormais du tunnel v2 :

    prospect.data_extra.email_objet / email_corps (et variantes *_2 .. *_4)
        → sequence_engine.send_initial / send_relance → gateway.envoyer

Les relances v2 se gèrent dans l'UI « Séquence » de la campagne
(`template_registry`, positions 0..3).

Ce stub ne conserve que la SURFACE de compat pour les modules legacy encore
chargés par la coquille V5 (`sniper/email_generator.py`,
`services/email_sequence_service.py`) : les constantes sont VIDE et
`get_mail_1()` retourne un dict vide en loggant un avertissement DEPRECATED.
Aucun envoi ne peut être alimenté par ce module.
"""
import logging

logger = logging.getLogger(__name__)

MAIL_1_BY_SECTOR = {}
MAIL_2_J3 = {"subject": "", "body": ""}
MAIL_3_J7 = {"subject": "", "body": ""}
MAIL_4_J14 = {"subject": "", "body": ""}


def get_mail_1(secteur: str) -> dict:
    """STUB (purge V1) : aucun contenu, avertissement DEPRECATED."""
    logger.warning(
        "DEPRECATED: envoi.sequence_emails.get_mail_1(secteur=%r) est un stub "
        "de purge V1 — aucun contenu. Le contenu provient du tunnel v2 "
        "(sequence_engine → gateway).", secteur)
    return {"subject": "", "body": ""}