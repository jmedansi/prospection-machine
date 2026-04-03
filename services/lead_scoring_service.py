import sqlite3
from datetime import datetime
import json

class LeadScoringService:
    """Calculer et mettre à jour le score des leads"""
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.POINTS = {
            'email_sent': 1,
            'email_opened': 10,
            'link_clicked': 50,
            'response_received': 100,
            'daily_decay': -5  # Par jour depuis la dernière interaction
        }
    def calculate_lead_score(self, lead_id: int) -> int:
        """Calculer le score total d'un lead"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        score = 0
        # Points pour envois
        cursor.execute("""
            SELECT COUNT(*) FROM email_events 
            WHERE lead_id = ? AND event_type = 'sent'
        """, (lead_id,))
        sent_count = cursor.fetchone()[0]
        score += sent_count * self.POINTS['email_sent']
        # Points pour ouvertures
        cursor.execute("""
            SELECT COUNT(*) FROM email_events 
            WHERE lead_id = ? AND event_type = 'opened'
        """, (lead_id,))
        opened_count = cursor.fetchone()[0]
        score += opened_count * self.POINTS['email_opened']
        # Points pour clics
        cursor.execute("""
            SELECT COUNT(*) FROM email_events 
            WHERE lead_id = ? AND event_type = 'clicked'
        """, (lead_id,))
        clicked_count = cursor.fetchone()[0]
        score += clicked_count * self.POINTS['link_clicked']
        # Points pour réponses
        cursor.execute("""
            SELECT COUNT(*) FROM email_events 
            WHERE lead_id = ? AND event_type IN ('replied', 'responded')
        """, (lead_id,))
        response_count = cursor.fetchone()[0]
        score += response_count * self.POINTS['response_received']
        # Décroissance temporelle
        cursor.execute("""
            SELECT MAX(timestamp) FROM email_events 
            WHERE lead_id = ?
        """, (lead_id,))
        last_interaction = cursor.fetchone()[0]
        if last_interaction:
            last_date = datetime.fromisoformat(last_interaction)
            days_since = (datetime.now() - last_date).days
            score += days_since * self.POINTS['daily_decay']
        score = max(0, score)
        conn.close()
        return score
    def classify_temperature(self, score: int) -> str:
        """Classer la température d'un lead"""
        if score >= 100:
            return 'chaud'
        elif score >= 30:
            return 'tiede'
        else:
            return 'froid'
    def update_lead_score(self, lead_id: int) -> tuple:
        """Calculer et persister le score + température"""
        score = self.calculate_lead_score(lead_id)
        temperature = self.classify_temperature(score)
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE emails_envoyes
                SET 
                    score_lead = ?,
                    lead_temperature = ?,
                    derniere_interaction = ?
                WHERE lead_id = ?
            """, (score, temperature, datetime.now().isoformat(), lead_id))
            conn.commit()
            return (score, temperature)
        finally:
            conn.close()
    def get_hot_leads(self, min_temperature: str = 'chaud', limit: int = 50) -> list:
        """Récupérer les leads chauds pour relance"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        temp_values = []
        if min_temperature == 'chaud':
            temp_values = ['chaud']
        elif min_temperature == 'tiede':
            temp_values = ['chaud', 'tiede']
        else:
            temp_values = ['froid', 'tiede', 'chaud']
        placeholders = ','.join('?' * len(temp_values))
        cursor.execute(f"""
            SELECT * FROM emails_envoyes
            WHERE lead_temperature IN ({placeholders})
            ORDER BY score_lead DESC
            LIMIT ?
        """, (*temp_values, limit))
        leads = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
        conn.close()
        return leads
