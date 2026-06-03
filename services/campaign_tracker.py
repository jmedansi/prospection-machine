# -*- coding: utf-8 -*-
"""
services/campaign_tracker.py — Status Registry centralisé pour les campagnes

Point unique de gestion du cycle de vie des campagnes.
Chaque campagne passe par les phases :
    pending → scraping → enrichment → audit → email_gen → done
    (avec possibilité de tomber en 'failed' ou 'stopped' à n'importe quelle phase)
"""

import json
import logging
from datetime import datetime
from database.connection import get_conn

logger = logging.getLogger(__name__)

# ─── Phases valides ───────────────────────────────────────────────────────────

PHASES = ('pending', 'scraping', 'enrichment', 'audit', 'email_gen', 'done', 'failed', 'stopped')
TERMINAL_PHASES = ('done', 'failed', 'stopped')


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# ─── Création & Démarrage ─────────────────────────────────────────────────────

def create_campaign(nom: str, secteur: str = '', ville: str = '',
                    source: str = 'maps', nb_demande: int = 0) -> int:
    """
    Crée une nouvelle campagne en DB et retourne son ID.
    Appelé AVANT le lancement du scraper.
    """
    try:
        with get_conn() as conn:
            cur = conn.execute("""
                INSERT INTO campagnes (nom, secteur, ville, source, nb_demande, phase, started_at)
                VALUES (?, ?, ?, ?, ?, 'pending', ?)
            """, (nom, secteur, ville, source, nb_demande, _now()))
            conn.commit()
            campaign_id = cur.lastrowid
            logger.info(f"[TRACKER] Campagne #{campaign_id} créée : {nom} ({source})")
            return campaign_id
    except Exception as e:
        logger.error(f"[TRACKER] create_campaign({nom}) → {e}")
        raise


def start_campaign(campaign_id: int, phase: str = 'scraping') -> None:
    """Marque le début d'une campagne (passage de pending à la phase active)."""
    if phase not in PHASES:
        raise ValueError(f"Phase invalide: {phase}")
    try:
        with get_conn() as conn:
            conn.execute("""
                UPDATE campagnes
                SET phase = ?, started_at = COALESCE(started_at, ?), error_message = NULL
                WHERE id = ?
            """, (phase, _now(), campaign_id))
            conn.commit()
        logger.info(f"[TRACKER] Campagne #{campaign_id} → phase={phase}")
    except Exception as e:
        logger.error(f"[TRACKER] start_campaign({campaign_id}) → {e}")


# ─── Mise à jour de progression ───────────────────────────────────────────────

def update_progress(campaign_id: int, processed: int = 0, total: int = 0,
                    emails_found: int = 0, phase: str = None,
                    phase_detail: str = '') -> None:
    """Met à jour la progression d'une campagne."""
    progress = json.dumps({
        'processed': processed,
        'total': total,
        'emails_found': emails_found,
        'phase_detail': phase_detail,
        'updated_at': _now(),
    })
    try:
        with get_conn() as conn:
            if phase:
                conn.execute("""
                    UPDATE campagnes
                    SET progress_data = ?, phase = ?, total_leads = ?
                    WHERE id = ?
                """, (progress, phase, processed, campaign_id))
            else:
                conn.execute("""
                    UPDATE campagnes
                    SET progress_data = ?, total_leads = ?
                    WHERE id = ?
                """, (progress, processed, campaign_id))
            conn.commit()
    except Exception as e:
        logger.error(f"[TRACKER] update_progress({campaign_id}) → {e}")


# ─── Fin & Erreurs ────────────────────────────────────────────────────────────

def complete_campaign(campaign_id: int) -> None:
    """Marque une campagne comme terminée avec succès."""
    try:
        with get_conn() as conn:
            # Récupérer le total actuel de leads
            row = conn.execute(
                "SELECT COUNT(*) FROM leads_bruts WHERE campaign_id = ?",
                (campaign_id,)
            ).fetchone()
            total = row[0] if row else 0

            conn.execute("""
                UPDATE campagnes
                SET phase = 'done', finished_at = ?, total_leads = ?, statut = 'done'
                WHERE id = ?
            """, (_now(), total, campaign_id))
            conn.commit()
        logger.info(f"[TRACKER] Campagne #{campaign_id} terminée ✓ ({total} leads)")
    except Exception as e:
        logger.error(f"[TRACKER] complete_campaign({campaign_id}) → {e}")


def fail_campaign(campaign_id: int, error_message: str, phase: str = None) -> None:
    """Marque un arrêt avec la raison d'erreur et la phase où ça s'est arrêté."""
    try:
        with get_conn() as conn:
            if phase:
                conn.execute("""
                    UPDATE campagnes
                    SET phase = 'failed', error_message = ?, stopped_at = ?,
                        statut = 'failed'
                    WHERE id = ?
                """, (f"[{phase}] {error_message}", _now(), campaign_id))
            else:
                conn.execute("""
                    UPDATE campagnes
                    SET phase = 'failed', error_message = ?, stopped_at = ?,
                        statut = 'failed'
                    WHERE id = ?
                """, (error_message, _now(), campaign_id))
            conn.commit()
        logger.warning(f"[TRACKER] Campagne #{campaign_id} ÉCHOUÉE : {error_message}")
    except Exception as e:
        logger.error(f"[TRACKER] fail_campaign({campaign_id}) → {e}")


def stop_campaign(campaign_id: int, reason: str = 'Arrêt utilisateur') -> None:
    """Arrêt manuel demandé par l'utilisateur (reprise possible)."""
    try:
        with get_conn() as conn:
            conn.execute("""
                UPDATE campagnes
                SET phase = 'stopped', error_message = ?, stopped_at = ?,
                    statut = 'stopped'
                WHERE id = ?
            """, (reason, _now(), campaign_id))
            conn.commit()
        logger.info(f"[TRACKER] Campagne #{campaign_id} arrêtée : {reason}")
    except Exception as e:
        logger.error(f"[TRACKER] stop_campaign({campaign_id}) → {e}")


def reset_all_active_campaigns(reason: str = "Force Stop") -> int:
    """
    Force l'arrêt de TOUTES les campagnes en cours en DB.
    Utilisé lors d'un 'Force Stop' global pour synchroniser l'UI.
    """
    try:
        with get_conn() as conn:
            cur = conn.execute("""
                UPDATE campagnes
                SET phase = 'stopped', error_message = ?, stopped_at = ?,
                    statut = 'stopped'
                WHERE phase IN ('scraping', 'enrichment', 'audit', 'email_gen', 'sending')
            """, (reason, _now()))
            conn.commit()
            count = cur.rowcount
            if count > 0:
                logger.warning(f"[TRACKER] {count} campagnes actives forcées à 'stopped'")
            return count
    except Exception as e:
        logger.error(f"[TRACKER] reset_all_active_campaigns → {e}")
        return 0


# ─── Requêtes ─────────────────────────────────────────────────────────────────

def get_campaign_state(campaign_id: int) -> dict | None:
    """Retourne l'état complet d'une campagne."""
    try:
        with get_conn() as conn:
            row = conn.execute("""
                SELECT c.*,
                    (SELECT COUNT(*) FROM leads_bruts WHERE campaign_id = c.id) as real_leads,
                    (SELECT COUNT(*) FROM leads_bruts WHERE campaign_id = c.id
                        AND email IS NOT NULL AND email != '') as real_emails
                FROM campagnes c WHERE c.id = ?
            """, (campaign_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            # Parse progress_data JSON
            if d.get('progress_data'):
                try:
                    d['progress'] = json.loads(d['progress_data'])
                except (json.JSONDecodeError, TypeError):
                    d['progress'] = {}
            else:
                d['progress'] = {}
            return d
    except Exception as e:
        logger.error(f"[TRACKER] get_campaign_state({campaign_id}) → {e}")
        return None


def get_resumable_campaigns() -> list:
    """Liste les campagnes arrêtées ou échouées qui peuvent être reprises."""
    try:
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT c.*,
                    (SELECT COUNT(*) FROM leads_bruts WHERE campaign_id = c.id) as real_leads
                FROM campagnes c
                WHERE c.phase IN ('failed', 'stopped')
                ORDER BY c.stopped_at DESC
                LIMIT 20
            """).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"[TRACKER] get_resumable_campaigns() → {e}")
        return []


def get_all_campaigns_with_status(limit: int = 50, sector: str = None) -> list:
    """
    Retourne les dernières campagnes avec leurs champs de suivi.
    Utilisé par GET /api/campaigns pour le nouveau tableau Sources.
    """
    try:
        with get_conn() as conn:
            base = """
                SELECT
                    c.id, c.nom, c.secteur, c.ville, c.date_creation,
                    c.nb_demande, c.source, c.phase, c.error_message,
                    c.started_at, c.finished_at, c.stopped_at, c.progress_data,
                    (SELECT COUNT(*) FROM leads_bruts WHERE campaign_id = c.id) as leads_total,
                    (SELECT COUNT(*) FROM leads_bruts WHERE campaign_id = c.id
                        AND email IS NOT NULL AND email != '') as leads_with_email,
                    (SELECT COUNT(*) FROM leads_bruts WHERE campaign_id = c.id
                        AND statut IN ('audite','email_genere','envoye')) as nb_audites,
                    (SELECT COUNT(*) FROM emails_envoyes ee
                        JOIN leads_bruts lb ON ee.lead_id = lb.id
                        WHERE lb.campaign_id = c.id) as emails_envoyes
                FROM campagnes c
            """
            where = ""
            params = []
            if sector:
                where = " WHERE LOWER(c.secteur) = LOWER(?)"
                params.append(sector)
            params.append(limit)
            rows = conn.execute(f"{base} {where} ORDER BY c.id DESC LIMIT ?", params).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                if d.get('progress_data'):
                    try:
                        d['progress'] = json.loads(d['progress_data'])
                    except (json.JSONDecodeError, TypeError):
                        d['progress'] = {}
                else:
                    d['progress'] = {}
                result.append(d)
            return result
    except Exception as e:
        logger.error(f"[TRACKER] get_all_campaigns_with_status() → {e}")
        return []
