import sqlite3
from datetime import datetime
from typing import Optional, Dict, Any

class EmailTrackingService:
    """Service centralisé pour toutes les opérations sur emails_envoyes"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def _get_conn(self):
        """Obtenir une connexion avec row_factory"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    # ========== OPÉRATIONS DE BASE ==========
    
    def create_email_record(
        self,
        lead_id: int,
        email: str,
        subject: str,
        body: str,
        lien_rapport: Optional[str] = None,
        approuve: int = 0
    ) -> int:
        """
        Créer un nouvel enregistrement dans emails_envoyes.
        Retourne l'ID de l'enregistrement créé.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO emails_envoyes 
                (lead_id, email, sujet, corps, lien_rapport, approuve, date_creation)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (lead_id, email, subject, body, lien_rapport, approuve, datetime.now().isoformat()))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()
    
    def update_rapport_link(
        self,
        email_record_id: int,
        lead_id: int,
        lien_rapport: str
    ) -> bool:
        """
        TRANSACTION ATOMIQUE: Mettre à jour lien_rapport dans les DEUX tables.
        - leads_audites.lien_rapport
        - emails_envoyes.lien_rapport
        
        Retourne True si succès, False si erreur.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            if not self._validate_rapport_link(lien_rapport):
                conn.rollback()
                return False
            cursor.execute("""
                UPDATE leads_audites 
                SET lien_rapport = ? 
                WHERE id = ?
            """, (lien_rapport, lead_id))
            cursor.execute("""
                UPDATE emails_envoyes 
                SET lien_rapport = ? 
                WHERE id = ?
            """, (lien_rapport, email_record_id))
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            print(f"Erreur update_rapport_link: {e}")
            return False
        finally:
            conn.close()
    
    def update_message_id(
        self,
        email_record_id: int,
        message_id_resend: str
    ) -> bool:
        """
        Mettre à jour message_id_resend après envoi réussi.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE emails_envoyes 
                SET message_id_resend = ?, date_envoi = ?
                WHERE id = ?
            """, (message_id_resend, datetime.now().isoformat(), email_record_id))
            conn.commit()
            return True
        except Exception as e:
            print(f"Erreur update_message_id: {e}")
            return False
        finally:
            conn.close()
    
    def mark_send_error(
        self,
        email_record_id: int,
        error_message: str,
        retry_count: int = 0
    ) -> bool:
        """
        Marquer un email comme ayant échoué à l'envoi.
        Incrémenter le nombre de tentatives.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE emails_envoyes 
                SET 
                    statut_envoi = 'erreur',
                    message_erreur = ?,
                    nb_tentatives_envoi = ?,
                    date_dernier_essai = ?
                WHERE id = ?
            """, (error_message, retry_count, datetime.now().isoformat(), email_record_id))
            conn.commit()
            return True
        except Exception as e:
            print(f"Erreur mark_send_error: {e}")
            return False
        finally:
            conn.close()
    
    # ========== VALIDATION ==========
    
    def _validate_rapport_link(self, lien_rapport: str) -> bool:
        """
        Vérifier que le lien est valide avant l'enregistrer:
        - Commence par https://
        - N'est pas vide
        """
        if not lien_rapport:
            return False
        if not lien_rapport.startswith("https://"):
            print(f"Lien non HTTPS: {lien_rapport}")
            return False
        return True
    
    def get_email_record(self, email_record_id: int) -> Optional[Dict[str, Any]]:
        """Récupérer un enregistrement email"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM emails_envoyes WHERE id = ?", (email_record_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    # ========== MÉTHODES STATIQUES APPELÉES PAR LE WEBHOOK ==========

    @staticmethod
    def log_event(message_id: str, event_type: str, timestamp: str, meta: dict):
        """Enregistrer un événement dans email_events."""
        from database import db_manager
        db_manager.insert_email_event(message_id, event_type, timestamp, meta)

    @staticmethod
    def mark_opened(message_id: str, timestamp: str, meta: dict):
        """Marquer un email comme ouvert."""
        from database import db_manager

        # Mettre à jour ouvert et date_ouverture
        db_manager.update_email_tracking(message_id, {
            'ouvert': 1,
            'date_ouverture': timestamp,
        })

        # Incrémenter nb_ouvertures via SQL direct
        from database.db_manager import get_conn
        with get_conn() as conn:
            conn.execute(
                "UPDATE emails_envoyes SET nb_ouvertures = nb_ouvertures + 1 "
                "WHERE message_id_resend = ? OR message_id_brevo = ?",
                (message_id, message_id)
            )

    @staticmethod
    def mark_clicked(message_id: str, timestamp: str, meta: dict):
        """Marquer un email comme cliqué."""
        from database import db_manager
        db_manager.update_email_tracking(message_id, {
            'clique': 1,
            'date_clic': timestamp,
        })

    @staticmethod
    def mark_bounced(message_id: str, timestamp: str, meta: dict):
        """Marquer un email comme bounced."""
        from database import db_manager

        # Récupérer le type de bounce
        bounce_type = 'unknown'
        if meta and meta.get('details'):
            bounce_type = meta['details'].get('bounce_type', 'unknown')

        db_manager.update_email_tracking(message_id, {
            'bounce': 1,
            'statut_envoi': f'bounce_{bounce_type}',
        })
