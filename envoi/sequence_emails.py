# -*- coding: utf-8 -*-
"""
envoi/sequence_emails.py
Mails de séquence : Mail 1 (Jour J par secteur), J+3, J+7, J+14.
Utilisés directement, tels quels, sans template processing.
"""

MAIL_1_BY_SECTOR = {
    "immobilier": {
        "subject": "Vos leads du soir et du weekend",
        "body": """Bonjour [Prénom],

Quand un prospect remplit votre formulaire, que se passe-t-il ensuite ?

La plupart des agences envoient une réponse automatique. Mais si le prospect ne répond pas, le suivi s'arrête là. Il finit chez un concurrent qui a relancé.

Je mets en place un système complet : réponse en moins de 2 minutes, relances automatiques et personnalisées à J+1, J+3 et J+7, puis notification à votre équipe quand le prospect est chaud et prêt à être contacté.

Résultat : vous ne perdez plus aucun lead faute de suivi.

15 minutes pour voir si c'est pertinent pour vous ?

Jean-Marc DANSI"""
    },
    "courtage": {
        "subject": "Vos dossiers du soir et du weekend",
        "body": """Bonjour [Prénom],

Quand un particulier soumet une demande de simulation un soir ou un weekend, que se passe-t-il ensuite ?

La plupart des courtiers envoient une réponse automatique. Mais si le prospect ne rappelle pas, le suivi s'arrête. Il finit par signer avec un courtier qui l'a relancé.

Je mets en place un système complet : réponse en moins de 2 minutes, relances automatiques à J+1, J+3 et J+7, notification à votre équipe quand le prospect est prêt.

Résultat : vous ne perdez plus aucun dossier faute de suivi.

15 minutes pour voir si c'est pertinent pour vous ?

Jean-Marc DANSI"""
    },
    "concessionnaires": {
        "subject": "Vos prospects du soir et du weekend",
        "body": """Bonjour [Prénom],

Quand quelqu'un demande un essai ou un devis un soir ou un weekend, que se passe-t-il ensuite ?

La plupart des concessions envoient une réponse automatique. Mais sans relance structurée, ce prospect achète ailleurs dans les 48 heures.

Je mets en place un système complet : réponse en moins de 2 minutes, relances automatiques à J+1, J+3 et J+7, notification à votre vendeur quand le prospect est chaud.

Résultat : vous ne perdez plus aucune vente faute de suivi.

15 minutes pour voir si c'est pertinent pour vous ?

Jean-Marc DANSI"""
    },
    "cliniques": {
        "subject": "Vos patientes du soir et du weekend",
        "body": """Bonjour [Prénom],

Quand une patiente demande un renseignement sur une prestation un soir ou un weekend, que se passe-t-il ensuite ?

La plupart des cliniques envoient une réponse automatique. Mais sans relance, elle prend rendez-vous ailleurs dans les 24 heures.

Je mets en place un système complet : réponse en moins de 2 minutes, relances automatiques à J+1, J+3 et J+7, notification à votre équipe quand la patiente est prête à réserver.

Résultat : vous ne perdez plus aucune patiente faute de suivi.

15 minutes pour voir si c'est pertinent pour vous ?

Jean-Marc DANSI"""
    },
    "ecoles": {
        "subject": "Vos candidats du soir et du weekend",
        "body": """Bonjour [Prénom],

Quand un candidat s'informe sur une de vos formations un soir ou un weekend, que se passe-t-il ensuite ?

La plupart des écoles envoient une réponse automatique. Mais sans relance, ce candidat s'inscrit ailleurs avant le lendemain matin.

Je mets en place un système complet : réponse en moins de 2 minutes, relances automatiques à J+1, J+3 et J+7, notification à votre conseiller quand le candidat est prêt à s'inscrire.

Résultat : vous ne perdez plus aucun candidat faute de suivi.

15 minutes pour voir si c'est pertinent pour vous ?

Jean-Marc DANSI"""
    }
}

MAIL_2_J3 = {
    "subject": "Re: Vos leads du soir et du weekend",
    "body": """Bonjour,

Je me permets de revenir vers vous.

Avez-vous eu l'occasion de lire mon message de l'autre jour ?

Jean-Marc DANSI"""
}

MAIL_3_J7 = {
    "subject": "Une dernière question",
    "body": """Bonjour,

Est-ce que le suivi automatique de vos prospects est quelque chose que vous gérez déjà en interne, ou c'est un sujet ouvert pour vous ?

Jean-Marc DANSI"""
}

MAIL_4_J14 = {
    "subject": "Je ferme votre dossier",
    "body": """Bonjour,

Je n'ai pas eu de retour de votre part, donc je suppose que le timing n'est pas bon ou que le sujet n'est pas prioritaire pour vous.

Je ferme votre dossier pour l'instant. Si la question du suivi automatique de vos prospects devient un sujet dans les prochains mois, n'hésitez pas à me recontacter.

Jean-Marc DANSI"""
}


def get_mail_1(secteur: str) -> dict:
    """Retourne Mail 1 (Jour J) pour un secteur donné."""
    key = (secteur or "").strip().lower() if secteur else ""
    for k in MAIL_1_BY_SECTOR.keys():
        if k in key:
            return MAIL_1_BY_SECTOR[k]
    # Fallback: return first
    return list(MAIL_1_BY_SECTOR.values())[0] if MAIL_1_BY_SECTOR else {}



