# -*- coding: utf-8 -*-
from .connection import get_conn, logger


def update_crm_manual(email_id: int, data: dict):
    """Mise à jour manuelle CRM depuis le dashboard."""
    try:
        allowed = {'type_reponse', 'rdv_confirme', 'date_rdv',
                   'notes', 'repondu', 'date_reponse'}
        data = {k: v for k, v in data.items() if k in allowed}
        if not data:
            return
        sets = ', '.join(f"{k}=:{k}" for k in data)
        data['id'] = email_id
        with get_conn() as conn:
            conn.execute(
                f"UPDATE emails_envoyes SET {sets} WHERE id=:id", data
            )
    except Exception as e:
        logger.error(f"update_crm_manual({email_id}) → {e}")


def get_crm_counts(date_start: str | None = None, date_end: str | None = None) -> dict:
    """Retourne les compteurs CRM."""
    try:
        with get_conn() as conn:
            date_clause = ""
            params = []
            if date_start and date_end:
                date_clause = "AND DATE(ee.date_envoi) >= ? AND DATE(ee.date_envoi) <= ?"
                params = [date_start, date_end]

            counts = {}
            counts['tous'] = conn.execute(f"""
                SELECT COUNT(*) as n FROM emails_envoyes ee 
                LEFT JOIN leads_bruts lb ON lb.id = ee.lead_id 
                WHERE ee.message_id_resend IS NOT NULL {date_clause}
            """, params).fetchone()['n']
            
            base_sql = f"""
                SELECT COUNT(*) as n FROM emails_envoyes ee 
                LEFT JOIN leads_bruts lb ON lb.id = ee.lead_id 
                WHERE ee.bounce = 0 AND ee.spam = 0 {date_clause}
            """
            counts['ouverts'] = conn.execute(base_sql + " AND ee.ouvert = 1", params).fetchone()['n']
            counts['cliques'] = conn.execute(base_sql + " AND ee.clique = 1", params).fetchone()['n']
            counts['repondus'] = conn.execute(base_sql + " AND ee.repondu = 1", params).fetchone()['n']
            counts['positifs'] = conn.execute(base_sql + " AND ee.type_reponse = 'positive'", params).fetchone()['n']
            counts['bounces'] = conn.execute(f"SELECT COUNT(*) as n FROM emails_envoyes ee WHERE (ee.bounce = 1 OR ee.statut_envoi = 'bounced') {date_clause}", params).fetchone()['n']
            counts['spam'] = conn.execute(f"SELECT COUNT(*) as n FROM emails_envoyes ee WHERE (ee.spam = 1 OR ee.statut_envoi = 'spam') {date_clause}", params).fetchone()['n']
            
            return counts
    except Exception as e:
        logger.error(f"get_crm_counts → {e}")
        return {}


def get_crm_data(filter_type: str = 'tous', date_start: str | None = None, date_end: str | None = None) -> list:
    """Retourne les données CRM filtrées."""
    try:
        with get_conn() as conn:
            where_clauses = []
            params = []
            if filter_type == 'ouverts': where_clauses.append("ee.ouvert = 1")
            elif filter_type == 'cliques': where_clauses.append("ee.clique = 1")
            elif filter_type == 'repondus': where_clauses.append("ee.repondu = 1")
            elif filter_type == 'positifs': where_clauses.append("ee.type_reponse = 'positive'")
            elif filter_type == 'rdv': where_clauses.append("ee.rdv_confirme = 1")
            elif filter_type == 'bounces': where_clauses.append("(ee.bounce = 1 OR ee.statut_envoi = 'bounced')")
            elif filter_type == 'spam': where_clauses.append("(ee.spam = 1 OR ee.statut_envoi = 'spam')")
                
            if date_start and date_end:
                where_clauses.append("DATE(ee.date_envoi) >= ?")
                where_clauses.append("DATE(ee.date_envoi) <= ?")
                params.extend([date_start, date_end])
            
            where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
            sql = f"""
                SELECT COALESCE(lb.nom, 'Test') AS nom, COALESCE(lb.email, ee.email_objet) AS prospect_email, 
                       COALESCE(lb.ville, '-') AS ville, ee.*
                FROM emails_envoyes ee
                LEFT JOIN leads_bruts lb ON lb.id = ee.lead_id
                {where_sql}
                ORDER BY ee.date_envoi DESC
            """
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_crm_data({filter_type}) → {e}")
        return []
