import os
import json
import logging
import re
from datetime import datetime
from database.connection import get_conn

logger = logging.getLogger(__name__)

def score_lead(lead_id: int) -> int:
    """
    Évalue le lead à partir de ses données d'audit technique (Phase 3.3).
    Retourne le score (0-100) et l'enregistre dans leads_audites.score_temperature.
    """
    try:
        with get_conn() as conn:
            lead_row = conn.execute("SELECT * FROM leads_audites WHERE id=?", (lead_id,)).fetchone()
            
        if not lead_row:
            logger.error(f"[SCORING] Lead {lead_id} introuvable.")
            return 0
            
        lead = dict(lead_row)
        # On exclut les gros blobs et métadonnées inutiles pour le prompt
        exclude = {
            'rapport_html', 'screenshot_desktop', 'screenshot_mobile', 
            'email_corps', 'email_objet', 'rapport_resume', 'arguments',
            'id', 'lead_id', 'date_audit', 'statut', 'sheets_synced'
        }
        audit_data = {k: v for k, v in lead.items() if k not in exclude and v is not None}
        
        if not audit_data:
            logger.warning(f"[SCORING] Lead {lead_id} n'a pas de données d'audit exploitables.")
            return 0

        score = 50
        api_key = os.getenv("GROQ_API_KEY")
        if api_key:
            prompt = (
                f"Analyse cet audit technique de site web pour un prospect commercial.\n"
                f"Évalue à quel point ce prospect a un besoin URGENT de nos services "
                f"(refonte de site, SEO, création de site, correction de bugs).\n"
                f"Donne une note stricte de 0 à 100. 100 = site catastrophique / inexistant / urgence absolue. 0 = site parfait.\n"
                f"Renvoie UNIQUEMENT LE NOMBRE (ex: 85). Aucun autre texte.\n\n"
                f"Données de l'audit:\n{json.dumps(audit_data, indent=2)}"
            )
            try:
                from groq import Groq
                client = Groq(api_key=api_key)
                response = client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=10,
                    temperature=0.1,
                )
                answer = response.choices[0].message.content.strip()
                match = re.search(r'\d+', answer)
                if match:
                    score = int(match.group(0))
                    score = max(0, min(100, score))
            except Exception as e:
                logger.error(f"[SCORING] Erreur Groq pour lead {lead_id}: {e}")
        else:
            if not audit_data.get("site_web"): score = 90
            elif not audit_data.get("mobile_friendly", True): score = 80
            else: score = 30

        with get_conn() as conn:
            conn.execute("UPDATE leads_audites SET score_temperature=? WHERE id=?", (score, lead_id))
            conn.commit()
            
        logger.info(f"[SCORING] Lead {lead_id} évalué à {score}/100.")
        return score

    except Exception as e:
        logger.error(f"[SCORING] Erreur globale pour lead {lead_id}: {e}")
        return 0


class LeadScoringService:
    """Calculer et mettre à jour le score des leads"""

    def __init__(self):
        self.POINTS = {
            'email_sent':         1,
            'email_opened':       10,
            'link_clicked':       50,
            'response_received':  100,
            'daily_decay':        -5,
        }

    def calculate_lead_score(self, lead_id: int) -> int:
        with get_conn() as conn:
            score = 0
            for event, key in (
                ('sent',    'email_sent'),
                ('opened',  'email_opened'),
                ('clicked', 'link_clicked'),
            ):
                count = conn.execute(
                    "SELECT COUNT(*) FROM email_events WHERE lead_id=? AND event_type=?",
                    (lead_id, event)
                ).fetchone()[0]
                score += count * self.POINTS[key]

            resp = conn.execute(
                "SELECT COUNT(*) FROM email_events WHERE lead_id=? AND event_type IN ('replied','responded')",
                (lead_id,)
            ).fetchone()[0]
            score += resp * self.POINTS['response_received']

            last = conn.execute(
                "SELECT MAX(timestamp) FROM email_events WHERE lead_id=?",
                (lead_id,)
            ).fetchone()[0]
            if last:
                days_since = (datetime.now() - datetime.fromisoformat(last)).days
                score += days_since * self.POINTS['daily_decay']

        return max(0, score)

    def classify_temperature(self, score: int) -> str:
        if score >= 100: return 'chaud'
        if score >= 30:  return 'tiede'
        return 'froid'

    def update_lead_score(self, lead_id: int) -> tuple:
        score       = self.calculate_lead_score(lead_id)
        temperature = self.classify_temperature(score)
        with get_conn() as conn:
            conn.execute("""
                UPDATE emails_envoyes
                SET score_lead=?, lead_temperature=?, derniere_interaction=?
                WHERE lead_id=?
            """, (score, temperature, datetime.now().isoformat(), lead_id))
            conn.commit()
        return (score, temperature)

    def get_hot_leads(self, min_temperature: str = 'chaud', limit: int = 50) -> list:
        temp_map = {
            'chaud': ['chaud'],
            'tiede': ['chaud', 'tiede'],
        }
        temps = temp_map.get(min_temperature, ['froid', 'tiede', 'chaud'])
        placeholders = ','.join('?' * len(temps))
        with get_conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM emails_envoyes WHERE lead_temperature IN ({placeholders}) "
                f"ORDER BY score_lead DESC LIMIT ?",
                (*temps, limit)
            ).fetchall()
        return [dict(row) for row in rows]
