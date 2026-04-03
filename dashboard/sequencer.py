import sys
import os
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from database.db_manager import get_conn


def generate_followups():
    """Trouve les emails envoyés il y a 3 jours sans clic et crée un batch de relance."""
    with get_conn() as conn:
        leads_to_bump = conn.execute("""
            SELECT ee.lead_id, ee.email_destinataire, lb.nom 
            FROM emails_envoyes ee
            JOIN leads_bruts lb ON lb.id = ee.lead_id
            WHERE ee.clique = 0 AND ee.relance_count = 0
              AND datetime(ee.date_envoi) < datetime('now', '-3 days')
              AND datetime(ee.date_envoi) > datetime('now', '-5 days')
        """).fetchall()
        
        return [dict(l) for l in leads_to_bump]


if __name__ == "__main__":
    to_bump = generate_followups()
    print(f"Trouvé {len(to_bump)} relances potentielles.")
