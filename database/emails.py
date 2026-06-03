# -*- coding: utf-8 -*-
import json
from .connection import get_conn, logger


def insert_email_sent(data: dict) -> int | None:
    """Enregistre un email envoyé. Retourne l'id."""
    try:
        with get_conn() as conn:
            cur = conn.execute("""
                INSERT INTO emails_envoyes
                (lead_id, message_id_brevo, message_id_resend, email_destinataire,
                 email_objet, email_corps, lien_rapport, statut_envoi)
                VALUES
                (:lead_id, :message_id_brevo, :message_id_resend, :email_destinataire,
                 :email_objet, :email_corps, :lien_rapport, :statut_envoi)
            """, {
                'lead_id':          data.get('lead_id'),
                'message_id_brevo': data.get('message_id_brevo', ''),
                'message_id_resend': data.get('message_id_resend', data.get('message_id', '')),
                'email_destinataire': data.get('email_destinataire', ''),
                'email_objet':      data.get('email_objet', ''),
                'email_corps':      data.get('email_corps', ''),
                'lien_rapport':     data.get('lien_rapport', ''),
                'statut_envoi':     data.get('statut_envoi', 'envoye'),
            })
            return cur.lastrowid
    except Exception as e:
        logger.error(f"insert_email_sent → {e}")
        raise


def update_email_tracking(message_id: str, data: dict):
    """Mise à jour tracking depuis un webhook."""
    try:
        allowed = {
            'ouvert', 'date_ouverture', 'nb_ouvertures',
            'clique', 'date_clic', 'bounce', 'spam',
            'statut_envoi', 'repondu', 'date_reponse', 'type_reponse'
        }
        data = {k: v for k, v in data.items() if k in allowed}
        if not data:
            return
        sets = ', '.join(f"{k}=:{k}" for k in data)
        with get_conn() as conn:
            cur = conn.execute(
                f"UPDATE emails_envoyes SET {sets} "
                f"WHERE message_id_resend=:message_id OR message_id_brevo=:message_id",
                {'message_id': message_id, **data}
            )
            if cur.rowcount > 0:
                logger.info(f"SQL Update: Tracking mis à jour pour {message_id} ({cur.rowcount} lignes)")
            else:
                logger.warning(f"SQL Update: Aucun email trouvé pour l'ID {message_id}")
    except Exception as e:
        logger.error(f"update_email_tracking({message_id}) → {e}")


def insert_email_event(message_id: str, event_type: str, timestamp: str, meta: dict):
    """Insérer un événement dans email_events."""
    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT id, lead_id FROM emails_envoyes "
                "WHERE message_id_resend = ? OR message_id_brevo = ?",
                (message_id, message_id)
            ).fetchone()
            if not row:
                logger.warning(f"insert_email_event: aucun email trouvé pour {message_id}")
                return
            email_record_id, lead_id = row[0], row[1]
            conn.execute("""
                INSERT INTO email_events
                (email_record_id, lead_id, event_type, event_data, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (
                email_record_id,
                lead_id or 0,
                event_type,
                json.dumps(meta),
                timestamp
            ))
            logger.info(f"Email event logged: {event_type} for message_id {message_id}")
    except Exception as e:
        logger.error(f"insert_email_event({message_id}) → {e}")
