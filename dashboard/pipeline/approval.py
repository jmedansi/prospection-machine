# -*- coding: utf-8 -*-
"""
dashboard/pipeline/approval.py
Logique d'approbation des leads et gestion des délais de validation.
"""
import logging
import time
from database.db_manager import get_conn

logger = logging.getLogger(__name__)

def _get_setting(key, default=None):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM planning_settings WHERE key=?", (key,)).fetchone()
        return row['value'] if row else default

def _set_setting(key, value):
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO planning_settings (key, value) VALUES (?, ?)", (key, str(value)))
        conn.commit()

def _approve_batch(lead_ids: list):
    """Marque approuve=1 dans leads_audites pour les leads du lot."""
    if not lead_ids:
        return
    with get_conn() as conn:
        placeholders = ','.join('?' * len(lead_ids))
        conn.execute(
            f"UPDATE leads_audites SET approuve=1 WHERE lead_id IN ({placeholders})",
            lead_ids
        )
        conn.commit()
    logger.info(f"[PIPELINE-Approbation] {len(lead_ids)} leads approuvés pour envoi.")

def notify_new_audits():
    """
    Notifie Telegram des nouveaux audits prêts.
    """
    from core.telegram_adapter import notify
    
    last_notif = float(_get_setting('last_notif', 0))
    if (time.time() - last_notif) < 1800:
        return
    
    try:
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT la.lead_id, lb.nom, lb.source, la.email_objet
                FROM leads_audites la
                JOIN leads_bruts lb ON la.lead_id = lb.id
                WHERE la.email_corps IS NOT NULL AND la.email_corps != ''
                  AND la.approuve = 0
                  AND (la.email_objet IS NOT NULL AND la.email_objet != '')
                  AND (la.notified_at IS NULL OR la.notified_at = '')
                  AND (lb.site_web IS NOT NULL AND lb.site_web != '')
                ORDER BY la.lead_id DESC
                LIMIT 50
            """).fetchall()

            if not rows:
                return

            lead_ids = [r['lead_id'] for r in rows]
            placeholders = ','.join('?' * len(lead_ids))
            conn.execute(f"UPDATE leads_audites SET notified_at = datetime('now') WHERE lead_id IN ({placeholders})", lead_ids)
            conn.commit()

            # Grouper par source
            _SOURCE_LABELS = {
                "ads":      "🎯 Ads",
                "ecom":     "🛒 E-com",
                "jobs":     "💼 Jobs",
                "bodacc":   "📋 BODACC",
                "scraper":  "📍 Maps",
                "organic":  "🔍 Organique",
            }
            from collections import Counter
            counts = Counter(r['source'] or 'scraper' for r in rows)
            breakdown = "  ".join(
                f"{_SOURCE_LABELS.get(src, src.capitalize())} {n}"
                for src, n in sorted(counts.items())
            )

            msg = f"*Nouveaux audits prêts — {len(lead_ids)} email(s)*\n_{breakdown}_\n\n"
            for r in rows[:10]:
                src_label = _SOURCE_LABELS.get(r['source'] or 'scraper', '')
                nom = (r['nom'] or '')[:28]
                obj = (r['email_objet'] or '')[:38]
                msg += f"• {src_label} {nom}\n  _{obj}_\n"

            msg += "\n\n⏰ Ces emails seront auto-approuvés dans 5h si pas de validation."

            notify("Audits prêts", msg)
            _set_setting('last_notif', time.time())
            logger.info(f"[PIPELINE-Approbation] Notification Telegram: {len(lead_ids)} audits prêts")
            
    except Exception as e:
        logger.error(f"[PIPELINE-Approbation] notify_new_audits: {e}")

def auto_approve_after_timeout():
    """
    Auto-approve les emails non approuvés après 5 heures.
    """
    from core.telegram_adapter import notify
    
    try:
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT la.lead_id
                FROM leads_audites la
                JOIN leads_bruts lb ON la.lead_id = lb.id
                WHERE la.email_corps IS NOT NULL AND la.email_corps != ''
                  AND la.approuve = 0
                  AND (la.email_objet IS NOT NULL AND la.email_objet != '')
                  AND (la.notified_at IS NOT NULL AND la.notified_at != '')
                  AND (datetime(la.notified_at) < datetime('now', '-5 hours'))
                  AND (lb.site_web IS NOT NULL AND lb.site_web != '')
            """).fetchall()
            
            if not rows:
                return
            
            lead_ids = [r['lead_id'] for r in rows]
            placeholders = ','.join('?' * len(lead_ids))
            conn.execute(f"UPDATE leads_audites SET approuve=1 WHERE lead_id IN ({placeholders})", lead_ids)
            conn.commit()
            
            logger.info(f"[PIPELINE-Approbation] Auto-approval: {len(lead_ids)} leads approuvés après 5h")
            
            last_notif = float(_get_setting('last_auto_approve', 0))
            if lead_ids and (time.time() - last_notif) >= 3600:
                notify("Auto-approval", f"{len(lead_ids)} emails ont été auto-approuvés (5h sans validation)")
                _set_setting('last_auto_approve', time.time())
            
    except Exception as e:
        logger.error(f"[PIPELINE-Approbation] auto_approve_after_timeout: {e}")
