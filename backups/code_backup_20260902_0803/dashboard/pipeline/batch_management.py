# -*- coding: utf-8 -*-
"""
dashboard/pipeline/batch_management.py
Gestion des batches programmés sur Resend (Pending vs Queued).
"""
import logging
import json
from datetime import datetime, timedelta
from database.db_manager import get_conn
from .notifications import _notify_and_watch_batch, _notify_batch_sent
from .lead_selection import _get_leads_for_batch
from .scraper_loop import _run_scraping_sync

logger = logging.getLogger(__name__)

BATCH_SIZE = 50
TARGET_BATCHES = 4 # (2 pending + 2 queued)

try:
    import pytz
    TZ = pytz.timezone('Europe/Paris')
except ImportError:
    from datetime import timezone
    TZ = timezone.utc

def _now_paris() -> datetime:
    try: return datetime.now(TZ)
    except Exception: return datetime.now()

def _get_setting(key, default=None):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM planning_settings WHERE key=?", (key,)).fetchone()
        return row['value'] if row else default

def _set_setting(key, value):
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO planning_settings (key, value) VALUES (?, ?)", (key, str(value)))
        conn.commit()

def get_resend_daily_usage() -> int:
    try:
        today_str = _now_paris().strftime('%Y-%m-%d')
        with get_conn() as conn:
            r1 = conn.execute("SELECT SUM(nb_emails) as total FROM scheduled_batches WHERE status='pending' AND DATE(scheduled_at)=?", (today_str,)).fetchone()
            r2 = conn.execute("SELECT SUM(nb_emails) as total FROM scheduled_batches WHERE status='sent' AND DATE(scheduled_at)=?", (today_str,)).fetchone()
            return (r1['total'] or 0) + (r2['total'] or 0)
    except: return 0

def get_resend_quota_remaining() -> int:
    try:
        with get_conn() as conn:
            r = conn.execute("SELECT COUNT(*) as n FROM resend_accounts WHERE actif = 1").fetchone()
            quota = r['n'] * 100 if r else 100
            return max(0, quota - get_resend_daily_usage())
    except: return 100

def get_future_pending_batches() -> int:
    try:
        now_str = _now_paris().isoformat()
        with get_conn() as conn:
            r = conn.execute("SELECT COUNT(*) as n FROM scheduled_batches WHERE status='pending' AND scheduled_at > ?", (now_str,)).fetchone()
            return r['n'] if r else 0
    except: return 0

def get_future_queued_batches() -> int:
    try:
        now_str = _now_paris().isoformat()
        with get_conn() as conn:
            r = conn.execute("SELECT COUNT(*) as n FROM scheduled_batches WHERE status='queued' AND scheduled_at > ?", (now_str,)).fetchone()
            return r['n'] if r else 0
    except: return 0

def reconcile_batches():
    """Marque 'sent' les batches dont l'heure programmée est passée."""
    try:
        now_str = _now_paris().isoformat()
        with get_conn() as conn:
            just_sent = conn.execute("""
                SELECT batch_key, scheduled_at, nb_emails FROM scheduled_batches
                WHERE status='pending' AND scheduled_at <= ?
            """, (now_str,)).fetchall()
            if just_sent:
                conn.execute("UPDATE scheduled_batches SET status='sent' WHERE status='pending' AND scheduled_at <= ?", (now_str,))
                conn.commit()
        for batch in just_sent:
            _notify_batch_sent(batch['batch_key'], batch['scheduled_at'], batch['nb_emails'])
    except Exception as e:
        logger.error(f"[PIPELINE-Batch] reconcile error: {e}")

def get_next_available_slot() -> datetime:
    now = _now_paris()
    with get_conn() as conn:
        rows = conn.execute("SELECT scheduled_at FROM scheduled_batches WHERE status != 'cancelled'").fetchall()
        taken = {r['scheduled_at'][:16] for r in rows}
    d = now.date()
    if now.hour >= 14: d += timedelta(days=1)
    for _ in range(30):
        for hour in [10, 14]:
            try: slot = TZ.localize(datetime(d.year, d.month, d.day, hour, 0, 0))
            except: slot = datetime(d.year, d.month, d.day, hour, 0, 0)
            if slot <= now: continue
            if slot.isoformat()[:16] not in taken: return slot
        d += timedelta(days=1)
    return None

def create_batch(pending: bool = True) -> dict:
    try:
        if pending and get_resend_quota_remaining() < BATCH_SIZE: return None
        leads = _get_leads_for_batch(BATCH_SIZE)
        if len(leads) < BATCH_SIZE:
            logger.warning(f"[PIPELINE-Batch] Stock insuffisant ({len(leads)}/{BATCH_SIZE}) — scraping Maps automatique désactivé, créer des leads manuellement via le dashboard")
            # _run_scraping_sync(BATCH_SIZE - len(leads) + 10)  # DÉSACTIVÉ — plus de déclenchement automatique du scraper Maps
            leads = _get_leads_for_batch(BATCH_SIZE)
        if len(leads) < BATCH_SIZE: return None
        lead_ids = [l['id'] for l in leads]
        slot = get_next_available_slot()
        if not slot: return None
        batch_key = slot.strftime("%Y-%m-%d_%Hh")
        if pending:
            from envoi.resend_sender import schedule_email_batch
            m_ids = schedule_email_batch(lead_ids, slot)
            if not m_ids: return None
            with get_conn() as conn:
                conn.execute("INSERT OR REPLACE INTO scheduled_batches (batch_key, scheduled_at, status, nb_emails, lead_ids, message_ids) VALUES (?,?,'pending',?,?,?)", (batch_key, slot.isoformat(), len(m_ids), json.dumps(lead_ids), json.dumps(m_ids)))
                conn.commit()
            _notify_and_watch_batch(batch_key, slot, len(m_ids), lead_ids)
        else:
            with get_conn() as conn:
                conn.execute("INSERT OR REPLACE INTO scheduled_batches (batch_key, scheduled_at, status, nb_emails, lead_ids, message_ids) VALUES (?,?,'queued',?,?,'[]')", (batch_key, slot.isoformat(), BATCH_SIZE, json.dumps(lead_ids)))
                conn.commit()
        return {'batch_key': batch_key}
    except Exception as e:
        logger.error(f"[PIPELINE-Batch] create_batch error: {e}")
        return None

def push_queued_batches():
    try:
        if get_resend_quota_remaining() < BATCH_SIZE or get_future_pending_batches() >= 2: return
        with get_conn() as conn:
            batch = conn.execute("SELECT batch_key, scheduled_at, lead_ids FROM scheduled_batches WHERE status='queued' ORDER BY scheduled_at LIMIT 1").fetchone()
        if not batch: return
        lead_ids = json.loads(batch['lead_ids'])
        slot = datetime.fromisoformat(batch['scheduled_at'])
        from envoi.resend_sender import schedule_email_batch
        m_ids = schedule_email_batch(lead_ids, slot)
        if m_ids:
            with get_conn() as conn:
                conn.execute("UPDATE scheduled_batches SET status='pending', nb_emails=?, message_ids=? WHERE batch_key=?", (len(m_ids), json.dumps(m_ids), batch['batch_key']))
                conn.commit()
            _notify_and_watch_batch(batch['batch_key'], slot, len(m_ids), lead_ids)
    except Exception as e:
        logger.error(f"[PIPELINE-Batch] push_queued error: {e}")

def maintain_batch_slots():
    """Maintient 2 pending + 2 queued."""
    try:
        reconcile_batches()
        f_pending = get_future_pending_batches()
        f_queued = get_future_queued_batches()
        total = f_pending + f_queued
        if total < TARGET_BATCHES:
            for _ in range(TARGET_BATCHES - total):
                if f_pending < 2:
                    if create_batch(pending=True): f_pending += 1
                else:
                    if create_batch(pending=False): f_queued += 1
        if f_pending < 2 and f_queued > 0:
            push_queued_batches()
    except Exception as e:
        logger.error(f"[PIPELINE-Batch] maintain error: {e}")
