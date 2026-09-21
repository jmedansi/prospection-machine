# -*- coding: utf-8 -*-
"""
database/repos/emails_repo.py — Repository emails_envoyes + email_events
"""
from __future__ import annotations
import json
from database.connection import get_conn, logger


class EmailsRepo:

    def insert(self, data: dict) -> int | None:
        """Enregistre un email envoyé. Retourne l'id row."""
        try:
            with get_conn() as conn:
                cur = conn.execute("""
                    INSERT INTO emails_envoyes
                    (lead_id, message_id_resend, message_id_brevo,
                     email_destinataire, email_objet, email_corps,
                     lien_rapport, statut_envoi)
                    VALUES
                    (:lead_id, :message_id_resend, :message_id_brevo,
                     :email_destinataire, :email_objet, :email_corps,
                     :lien_rapport, :statut_envoi)
                """, {
                    "lead_id":            data.get("lead_id"),
                    "message_id_resend":  data.get("message_id_resend", data.get("message_id", "")),
                    "message_id_brevo":   data.get("message_id_brevo", ""),
                    "email_destinataire": data.get("email_destinataire", ""),
                    "email_objet":        data.get("email_objet", ""),
                    "email_corps":        data.get("email_corps", ""),
                    "lien_rapport":       data.get("lien_rapport", ""),
                    "statut_envoi":       data.get("statut_envoi", "envoye"),
                })
                conn.commit()
                return cur.lastrowid
        except Exception as e:
            logger.error(f"EmailsRepo.insert → {e}")
            raise

    def get_sent(self, limit: int = 50, statut: str | None = None) -> list[dict]:
        """Liste des emails envoyés, jointure nom lead."""
        try:
            where = ""
            params: list = []
            if statut:
                where = "WHERE ee.statut_envoi = ?"
                params.append(statut)
            with get_conn() as conn:
                rows = conn.execute(f"""
                    SELECT
                        ee.*,
                        lb.nom AS lead_nom, lb.ville, lb.category AS secteur
                    FROM emails_envoyes ee
                    LEFT JOIN leads_bruts lb ON lb.id = ee.lead_id
                    {where}
                    ORDER BY ee.date_envoi DESC
                    LIMIT ?
                """, params + [limit]).fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"EmailsRepo.get_sent → {e}")
            return []

    def update_tracking(self, message_id: str, fields: dict) -> bool:
        """Met à jour les données de tracking depuis un webhook."""
        allowed = {
            "ouvert", "date_ouverture", "nb_ouvertures",
            "clique", "date_clic", "bounce", "spam",
            "statut_envoi", "repondu", "date_reponse", "type_reponse",
        }
        data = {k: v for k, v in fields.items() if k in allowed}
        if not data:
            return False
        try:
            sets = ", ".join(f"{k}=:{k}" for k in data)
            with get_conn() as conn:
                cur = conn.execute(
                    f"UPDATE emails_envoyes SET {sets} "
                    f"WHERE message_id_resend=:mid OR message_id_brevo=:mid",
                    {"mid": message_id, **data},
                )
                conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            logger.error(f"EmailsRepo.update_tracking({message_id}) → {e}")
            return False

    def log_event(self, message_id: str, event_type: str,
                  timestamp: str, meta: dict) -> bool:
        """Insère un événement dans email_events."""
        try:
            with get_conn() as conn:
                row = conn.execute(
                    "SELECT id, lead_id FROM emails_envoyes "
                    "WHERE message_id_resend=? OR message_id_brevo=?",
                    (message_id, message_id)
                ).fetchone()
                if not row:
                    logger.warning(f"EmailsRepo.log_event: aucun email pour {message_id}")
                    return False
                conn.execute("""
                    INSERT INTO email_events
                    (email_record_id, lead_id, event_type, event_data, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                """, (row['id'], row['lead_id'] or 0, event_type, json.dumps(meta), timestamp))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"EmailsRepo.log_event({message_id}) → {e}")
            return False

    def get_stats(self) -> dict:
        """Statistiques globales emails (total, ouverts, cliqués, répondus)."""
        try:
            with get_conn() as conn:
                row = conn.execute("""
                    SELECT
                        COUNT(*)                           AS total,
                        SUM(ouvert)                        AS ouverts,
                        SUM(clique)                        AS cliques,
                        SUM(repondu)                       AS repondus,
                        SUM(rdv_confirme)                  AS rdv,
                        SUM(bounce)                        AS bounces,
                        SUM(spam)                          AS spams
                    FROM emails_envoyes
                """).fetchone()
                return dict(row) if row else {}
        except Exception as e:
            logger.error(f"EmailsRepo.get_stats → {e}")
            return {}


emails_repo = EmailsRepo()
