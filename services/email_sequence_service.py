import sqlite3
from datetime import datetime, timedelta
import json

class EmailSequenceService:
    """Gérer les séquences de relances"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def plan_sequences_for_lead(self, lead_id: int, initial_email_record_id: int):
        """
        Planifier les relances pour un lead après l'email initial.
        Séquence par défaut:
        - Jour 3: Relance 1 (pour les non-clics)
        - Jour 7: Relance 2 (pour les ouvertures sans clic)
        - Jour 14: Relance spéciale haute-valeur (si lead tiède/chaud)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        # Récupérer la date d'envoi initial
        cursor.execute("""
            SELECT date_envoi FROM emails_envoyes WHERE id = ?
        """, (initial_email_record_id,))
        row = cursor.fetchone()
        if not row or not row[0]:
            conn.close()
            return
        initial_send_date = datetime.fromisoformat(row[0])
        sequences = [
            {
                'email_type': 'relance_1',
                'days_offset': 3,
                'condition': json.dumps({'nb_clics': 0})
            },
            {
                'email_type': 'relance_2',
                'days_offset': 7,
                'condition': json.dumps({'nb_clics': 0, 'date_ouverture': True})
            },
            {
                'email_type': 'relance_special',
                'days_offset': 14,
                'condition': json.dumps({'lead_temperature': ['chaud', 'tiede']})
            }
        ]
        now = datetime.now()
        for seq in sequences:
            date_planifiee = initial_send_date + timedelta(days=seq['days_offset'])
            cursor.execute("""
                INSERT INTO email_sequences
                (lead_id, email_record_id, email_type, statut, date_planifiee, condition_envoi, created_at)
                VALUES (?, ?, ?, 'planned', ?, ?, ?)
            """, (
                lead_id,
                initial_email_record_id,
                seq['email_type'],
                date_planifiee.isoformat(),
                seq['condition'],
                now.isoformat()
            ))
        conn.commit()
        conn.close()
    
    def get_sequences_to_send(self) -> list:
        """Récupérer les séquences prêtes à être envoyées"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute("""
            SELECT 
                seq.*,
                ee.lead_id,
                ee.email_destinataire as email,
                ee.score_lead,
                ee.lead_temperature
            FROM email_sequences seq
            JOIN emails_envoyes ee ON seq.email_record_id = ee.id
            WHERE 
                seq.statut = 'planned'
                AND seq.date_planifiee <= ?
            ORDER BY seq.date_planifiee ASC
        """, (now,))
        sequences = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
        conn.close()
        return sequences
    
    def should_send_sequence(self, sequence: dict) -> bool:
        """Vérifier si les conditions sont respectées pour envoyer"""
        condition_str = sequence.get('condition_envoi')
        if not condition_str:
            return True
        try:
            condition = json.loads(condition_str)
        except:
            return True
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        lead_id = sequence['lead_id']
        # Vérifier les conditions
        if 'nb_clics' in condition:
            cursor.execute("""
                SELECT nb_clics FROM emails_envoyes WHERE lead_id = ?
            """, (lead_id,))
            row = cursor.fetchone()
            if row and row[0] >= condition['nb_clics']:
                conn.close()
                return False
        conn.close()
        return True
    
    def mark_sequence_sent(self, sequence_id: int, email_record_id: int):
        """Marquer une séquence comme envoyée"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE email_sequences
            SET statut = 'sent', date_envoi = ?
            WHERE id = ?
        """, (datetime.now().isoformat(), sequence_id))
        conn.commit()
        conn.close()
