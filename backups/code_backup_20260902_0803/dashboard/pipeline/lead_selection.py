# -*- coding: utf-8 -*-
"""
dashboard/pipeline/lead_selection.py
Logique de sélection des leads pour le pipeline et les batches.
"""
import logging
import json
from database.db_manager import get_conn

logger = logging.getLogger(__name__)

def get_leads_for_pipeline(limit: int = 60) -> list:
    """Leads avec email, non envoyés, triés par score_urgence DESC (gros problèmes en premier)."""
    try:
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT lb.id, lb.nom, lb.email, lb.ville, lb.category,
                       COALESCE(la.score_temperature, 0) AS score_temperature
                FROM leads_bruts lb
                LEFT JOIN leads_audites la ON la.lead_id = lb.id
                WHERE lb.email IS NOT NULL AND lb.email != ''
                  AND lb.statut NOT IN ('envoye', 'email_sent')
                  AND (lb.site_web IS NOT NULL AND lb.site_web != '')
                  AND lb.id NOT IN (
                      SELECT DISTINCT lead_id FROM emails_envoyes
                      WHERE lead_id IS NOT NULL
                  )
                  AND lb.id NOT IN (
                      SELECT lead_id FROM leads_audites
                      WHERE approuve = 1
                  )
                ORDER BY score_temperature DESC, lb.id DESC
                LIMIT ?
            """, (limit,)).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"[PIPELINE-Selection] get_leads_for_pipeline: {e}")
        return []

def _get_leads_for_batch(batch_size: int = 50) -> list:
    """
    Retourne jusqu'à batch_size leads avec email, non déjà dans un batch pending/sent/scheduled.
    """
    try:
        with get_conn() as conn:
            # Récupérer les lead_ids déjà dans des batches pending ou queued
            rows = conn.execute(
                "SELECT lead_ids FROM scheduled_batches WHERE status IN ('pending', 'queued')"
            ).fetchall()
            already_scheduled = set()
            for row in rows:
                if row['lead_ids']:
                    already_scheduled.update(json.loads(row['lead_ids']))

            candidates = conn.execute("""
                SELECT lb.id, lb.nom, lb.email, lb.ville, lb.category
                FROM leads_bruts lb
                JOIN leads_audites la ON la.lead_id = lb.id
                WHERE lb.email IS NOT NULL AND lb.email != ''
                  AND (lb.email_valide = 'Valide' OR lb.email_valide IS NULL)
                  AND lb.statut NOT IN ('envoye', 'email_sent', 'scheduled')
                  AND (lb.site_web IS NOT NULL AND lb.site_web != '')
                  AND la.approuve = 1
                  AND la.email_corps IS NOT NULL AND la.email_corps != ''
                ORDER BY la.score_temperature DESC, lb.id DESC
                LIMIT ?
            """, (batch_size * 4,)).fetchall()

        result = []
        for r in candidates:
            if r['id'] not in already_scheduled:
                result.append(dict(r))
            if len(result) >= batch_size:
                break
        return result
    except Exception as e:
        logger.error(f"[PIPELINE-Selection] _get_leads_for_batch: {e}")
        return []
