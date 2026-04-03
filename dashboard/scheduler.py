# -*- coding: utf-8 -*-
"""
dashboard/scheduler.py
Planificateur APScheduler — scraping automatique + envoi emails quotidien.

Chaque job enregistre son exécution dans scheduler_log (job_id + run_date).
Au démarrage, run_startup_catchup() vérifie les jobs manqués du jour et les rattrape.
"""
import os
import sys
import logging
import subprocess
import threading
from datetime import date, datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from database.db_manager import get_conn

logger = logging.getLogger(__name__)

_scheduler = None


# ──────────────────────────────────────────────────────────────────────────────
# SCHEDULER LOG
# ──────────────────────────────────────────────────────────────────────────────

def _log_job(job_id: str):
    """Enregistre qu'un job a tourné aujourd'hui."""
    try:
        with get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO scheduler_log (job_id, run_date, ran_at)
                VALUES (?, date('now'), datetime('now'))
            """, (job_id,))
            conn.commit()
    except Exception as e:
        logger.error(f"[SCHEDULER] _log_job {job_id}: {e}")


def _job_ran_today(job_id: str) -> bool:
    """Retourne True si ce job a déjà tourné aujourd'hui."""
    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM scheduler_log WHERE job_id=? AND run_date=date('now')",
                (job_id,)
            ).fetchone()
        return row is not None
    except Exception:
        return False


# ──────────────────────────────────────────────────────────────────────────────
# QUOTA
# ──────────────────────────────────────────────────────────────────────────────

def get_daily_quota() -> int:
    """Retourne le quota email du jour (avec ramp-up automatique)."""
    try:
        with get_conn() as conn:
            rows = {r['key']: r['value'] for r in conn.execute(
                "SELECT key, value FROM planning_settings"
            ).fetchall()}

        start_str = rows.get('quota_start_date', date.today().isoformat())
        start = date.fromisoformat(start_str)
        days_elapsed = (date.today() - start).days

        configured = int(rows.get('daily_quota', 100))
        if days_elapsed < 7:
            return min(50, configured)
        elif days_elapsed < 14:
            return min(100, configured)
        else:
            return configured
    except Exception as e:
        logger.error(f"get_daily_quota: {e}")
        return 30


def get_emails_sent_today() -> int:
    """Nombre d'emails envoyés aujourd'hui."""
    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as n FROM emails_envoyes WHERE date(date_envoi) = date('now')"
            ).fetchone()
            return row['n'] if row else 0
    except Exception:
        return 0


def get_quota_remaining() -> int:
    return max(0, get_daily_quota() - get_emails_sent_today())


# ──────────────────────────────────────────────────────────────────────────────
# SCRAPING PLANIFIÉ
# ──────────────────────────────────────────────────────────────────────────────

def run_planned_scrapings():
    """Lance les scrapings planifiés pour aujourd'hui."""
    today = date.today().isoformat()
    logger.info(f"[SCHEDULER] Vérification scrapings planifiés pour {today}")

    try:
        with get_conn() as conn:
            campaigns = conn.execute("""
                SELECT * FROM planned_campaigns
                WHERE date_planifiee = ? AND statut = 'planned'
                ORDER BY heure ASC
            """, (today,)).fetchall()
    except Exception as e:
        logger.error(f"[SCHEDULER] Erreur lecture planned_campaigns: {e}")
        return

    for c in campaigns:
        _launch_planned_campaign(dict(c))

    _log_job('planned_scrapings')


def _launch_planned_campaign(c: dict):
    """Lance un scraping planifié via l'API Flask interne."""
    try:
        import requests as req
        payload = {
            'keyword':       c['keyword'],
            'city':          c['city'],
            'sector':        c['secteur'],
            'campaign_name': f"{c['secteur']} {c['city']} {c['date_planifiee']}",
            'multi_zone':    False,
        }
        if c.get('min_emails'):
            payload['min_emails'] = c['min_emails']
            payload['limit']      = c['min_emails'] * 4
        else:
            payload['limit'] = c.get('limit_leads', 100)

        resp = req.post('http://127.0.0.1:5001/api/scraper/launch', json=payload, timeout=10)

        if resp.status_code == 200:
            campaign_id = resp.json().get('campaign_id')
            with get_conn() as conn:
                conn.execute(
                    "UPDATE planned_campaigns SET statut='running', campaign_id=? WHERE id=?",
                    (campaign_id, c['id'])
                )
                conn.commit()
            logger.info(f"[SCHEDULER] Scraping lancé: {c['keyword']} {c['city']}")
        else:
            logger.warning(f"[SCHEDULER] Erreur lancement: {resp.text}")

    except Exception as e:
        logger.error(f"[SCHEDULER] _launch_planned_campaign: {e}")


def mark_planned_done():
    """Marque comme 'done' les campagnes running dont le scraper est terminé."""
    try:
        with get_conn() as conn:
            conn.execute("""
                UPDATE planned_campaigns SET statut = 'done'
                WHERE statut = 'running'
                  AND campaign_id IS NOT NULL
                  AND campaign_id IN (
                      SELECT id FROM campagnes WHERE date_creation < datetime('now', '-1 hour')
                  )
            """)
            conn.commit()
    except Exception as e:
        logger.error(f"[SCHEDULER] mark_planned_done: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# ENVOI EMAILS
# ──────────────────────────────────────────────────────────────────────────────

def _send_email_batch(slot_name: str, limit: int):
    """Envoie un lot d'emails directement (sans passer par l'API Flask)."""
    remaining = get_quota_remaining()
    if remaining <= 0:
        logger.info(f"[SCHEDULER] {slot_name} — quota atteint.")
        return

    to_send = min(limit, remaining)
    logger.info(f"[SCHEDULER] {slot_name} : envoi de {to_send} emails")

    try:
        import subprocess
        from envoi.resend_sender import send_prospecting_email

        with get_conn() as conn:
            leads = conn.execute("""
                SELECT lb.id, lb.email, lb.nom,
                       la.email_objet, la.email_corps, la.lien_rapport, la.template_variant
                FROM leads_bruts lb
                JOIN leads_audites la ON la.lead_id = lb.id
                WHERE lb.email IS NOT NULL AND lb.email != ''
                  AND la.approuve = 1
                  AND lb.statut NOT IN ('envoye', 'email_sent')
                  AND lb.id NOT IN (
                      SELECT DISTINCT lead_id FROM emails_envoyes WHERE lead_id IS NOT NULL
                  )
                ORDER BY la.score_urgence DESC LIMIT ?
            """, (to_send,)).fetchall()

        sent = 0
        errors = []
        for lead in leads:
            try:
                result = send_prospecting_email(
                    prospect_email=lead['email'],
                    prospect_nom=lead['nom'],
                    email_objet=lead['email_objet'],
                    email_corps=lead['email_corps'],
                    lien_rapport=lead['lien_rapport'],
                )
                if result['success']:
                    with get_conn() as conn:
                        conn.execute("""
                            INSERT INTO emails_envoyes
                                (lead_id, message_id_resend, email_objet, email_corps,
                                 lien_rapport, email_destinataire, statut_envoi, template_variant)
                            VALUES (?, ?, ?, ?, ?, ?, 'envoye', ?)
                        """, (lead['id'], result.get('message_id'),
                              lead['email_objet'], lead['email_corps'],
                              lead['lien_rapport'], lead['email'], lead.get('template_variant', 'v1')))
                        conn.execute(
                            "UPDATE leads_bruts SET statut='envoye' WHERE id=?",
                            (lead['id'],)
                        )
                        conn.commit()
                    sent += 1
                else:
                    errors.append(f"{lead['nom']}: {result.get('erreur')}")
            except Exception as e:
                errors.append(f"{lead['nom']}: {e}")

        logger.info(f"[SCHEDULER] {slot_name} : {sent}/{len(leads)} emails envoyés.")

        # Notification Telegram
        _notify_telegram_sent(slot_name, sent, len(leads), errors)

    except Exception as e:
        logger.error(f"[SCHEDULER] {slot_name}: {e}")


def _notify_telegram_sent(slot_name: str, sent: int, attempted: int, errors: list):
    """Envoie une notification Telegram après un batch d'envoi."""
    try:
        import sys
        sys.path.insert(0, HUB_TELEGRAM)
        from telegram_notifier import notify
        msg = f"{sent}/{attempted} emails envoyes"
        if errors:
            msg += f" | {len(errors)} erreur(s)"
        notify(f"Envoi {slot_name}", msg)
    except Exception:
        pass  # Telegram non critique


# ──────────────────────────────────────────────────────────────────────────────
# BLOG INCIDENX
# ──────────────────────────────────────────────────────────────────────────────

BLOG_PIPELINE = "D:/IncidenX/scripts/daily_blog_pipeline.py"
BLOG_STATE = "D:/IncidenX/scripts/state.json"


def _check_blog_already_run_today(count: int) -> bool:
    """Vérifie si on a déjà publié count articles aujourd'hui"""
    import json
    try:
        if os.path.exists(BLOG_STATE):
            with open(BLOG_STATE, 'r') as f:
                state = json.load(f)
            today = datetime.now().strftime('%Y-%m-%d')
            if state.get('last_run_date') == today:
                published = state.get('articles_published_today', [])
                return len(published) >= count
    except:
        pass
    return False


def publish_blog_articles(count: int = 1):
    """Publie un ou plusieurs articles sur le blog IncidenX"""
    if _check_blog_already_run_today(count):
        logger.info(f"[BLOG] {count} article(s) deja publie(s) aujourd'hui")
        return
    
    if not os.path.exists(BLOG_PIPELINE):
        logger.error(f"[BLOG] Script introuvable: {BLOG_PIPELINE}")
        return
    
    try:
        logger.info(f"[BLOG] Publication de {count} article(s)...")
        result = subprocess.run(
            [sys.executable, BLOG_PIPELINE, "--count", str(count), "--push"],
            cwd=os.path.dirname(BLOG_PIPELINE),
            capture_output=True,
            text=True,
            timeout=600
        )
        
        if result.returncode == 0:
            logger.info(f"[BLOG] {count} article(s) publie(s) avec succes")
            _notify_blog_published(count)
        else:
            logger.error(f"[BLOG] Erreur: {result.stderr[:200]}")
            
    except subprocess.TimeoutExpired:
        logger.error("[BLOG] Timeout - article trop long")
    except Exception as e:
        logger.error(f"[BLOG] Erreur: {e}")


def _notify_blog_published(count: int):
    """Notification Telegram après publication blog"""
    try:
        sys.path.insert(0, HUB_TELEGRAM)
        from telegram_notifier import notify
        notify(f"Blog IncidenX", f"{count} article(s) publie(s)!")
    except:
        pass


def publish_blog_1():
    """Job 08h00 - 1 article le matin"""
    publish_blog_articles(1)
    _log_job('blog_article_1')


def publish_blog_2():
    """Job 12h00 - 1 article midi"""
    publish_blog_articles(1)
    _log_job('blog_article_2')


def publish_blog_3():
    """Job 17h00 - 1 article soir"""
    publish_blog_articles(1)
    _log_job('blog_article_3')


def send_morning_emails():
    """DEPRECATED — les envois passent par Resend scheduled batches."""
    logger.info("[SCHEDULER] send_morning_emails() DEPRECATED — géré par Resend scheduled batches")


def send_afternoon_emails():
    """DEPRECATED — les envois passent par Resend scheduled batches."""
    logger.info("[SCHEDULER] send_afternoon_emails() DEPRECATED — géré par Resend scheduled batches")


def _run_auto_plan():
    """Lance l'auto-planificateur (job 07h45)."""
    try:
        from auto_planner import run_auto_plan
        run_auto_plan()
        _log_job('auto_plan')
    except Exception as e:
        logger.error(f"[SCHEDULER] _run_auto_plan: {e}")


def run_pipeline():
    """Lance le pipeline soirée (legacy — remplacé par run_fill_check)."""
    try:
        from pipeline import run_evening_pipeline
        run_evening_pipeline()
        _log_job('evening_pipeline')
    except Exception as e:
        logger.error(f"[SCHEDULER] run_pipeline: {e}")


def run_fill_check():
    """
    Vérification réactive : s'assure qu'il y a toujours 2 batches pending et 2 batches queued.
    Lance maintain_batch_slots() dans un thread si nécessaire.
    Appelé au démarrage et toutes les heures.
    """
    try:
        from pipeline import reconcile_batches, count_future_batches, maintain_batch_slots, push_queued_batches, fill_incomplete_batches, TARGET_BATCHES, get_future_pending_batches, get_future_queued_batches, notify_new_audits, auto_approve_after_timeout
        reconcile_batches()
        # 1. Compléter les batches incomplets (< 50 emails)
        threading.Thread(target=fill_incomplete_batches, daemon=True).start()
        # 2. Pousser les batches queued sur Resend si le quota est disponible (un seul à la fois)
        threading.Thread(target=push_queued_batches, daemon=True).start()
        
        future_pending = get_future_pending_batches()
        future_queued = get_future_queued_batches()
        future_total = future_pending + future_queued
        
        if future_total < TARGET_BATCHES:
            logger.info(f"[SCHEDULER] Fill check: pending={future_pending}, queued={future_queued}, total={future_total}/4 — lancement pipeline")
            threading.Thread(target=maintain_batch_slots, daemon=True).start()
        else:
            logger.info(f"[SCHEDULER] Fill check: pending={future_pending}, queued={future_queued}, total={future_total}/4 — OK")
    except Exception as e:
        logger.error(f"[SCHEDULER] run_fill_check: {e}")


def send_daily_recap():
    """
    Envoie un récapitulatif quotidien via Telegram.
    Inclut : quota Resend, batches en attente, leads scrapés, emails envoyés, etc.
    """
    try:
        from telegram_notifier import notify
        from database.db_manager import get_conn
        
        today = date.today().isoformat()
        with get_conn() as conn:
            # Statistiques du jour
            # 1. Batches créés aujourd'hui
            batches_today = conn.execute("""
                SELECT COUNT(*) as total, SUM(nb_emails) as total_emails
                FROM scheduled_batches
                WHERE DATE(created_at) = ?
            """, (today,)).fetchone()
            nb_batches = batches_today['total'] if batches_today else 0
            nb_emails_in_batches = batches_today['total_emails'] if batches_today else 0
            
            # 2. Emails envoyés aujourd'hui
            emails_sent = conn.execute("""
                SELECT COUNT(*) as total
                FROM emails_envoyes
                WHERE DATE(date_envoi) = ?
            """, (today,)).fetchone()
            nb_sent = emails_sent['total'] if emails_sent else 0
            
            # 3. Leads scrapés aujourd'hui
            leads_scraped = conn.execute("""
                SELECT COUNT(*) as total
                FROM leads_bruts
                WHERE DATE(date_scraping) = ?
            """, (today,)).fetchone()
            nb_scraped = leads_scraped['total'] if leads_scraped else 0
            
            # 4. Leads en attente (prêts pour audit/email)
            leads_pending = conn.execute("""
                SELECT COUNT(*) as total
                FROM leads_bruts
                WHERE statut = 'en_attente'
            """).fetchone()
            nb_pending = leads_pending['total'] if leads_pending else 0
            
            # 5. Batches pending/queued
            batches_pending = conn.execute("""
                SELECT COUNT(*) as total
                FROM scheduled_batches
                WHERE status = 'pending' AND DATE(scheduled_at) > ?
            """, (today,)).fetchone()
            nb_pending_batches = batches_pending['total'] if batches_pending else 0
            
            batches_queued = conn.execute("""
                SELECT COUNT(*) as total
                FROM scheduled_batches
                WHERE status = 'queued' AND DATE(scheduled_at) > ?
            """, (today,)).fetchone()
            nb_queued_batches = batches_queued['total'] if batches_queued else 0
            
            # 6. Quota Resend
            from pipeline import get_resend_daily_usage, RESEND_DAILY_LIMIT
            resend_used = get_resend_daily_usage()
            resend_remaining = max(0, RESEND_DAILY_LIMIT - resend_used)
        
        # Message de récap
        msg = f"*Récap quotidien — {today}*\n\n"
        msg += f"• *{nb_sent}* emails envoyés aujourd'hui\n"
        msg += f"• *{nb_batches}* batches créés ({nb_emails_in_batches} emails programmés)\n"
        msg += f"• *{nb_scraped}* leads scrapés\n"
        msg += f"• *{nb_pending}* leads en attente d'audit\n"
        msg += f"• *{resend_used}/{RESEND_DAILY_LIMIT}* quota Resend utilisé (restant: {resend_remaining})\n"
        msg += f"• *{nb_pending_batches}* batches pending (sur Resend)\n"
        msg += f"• *{nb_queued_batches}* batches queued (en attente locale)\n"
        
        notify("Récap quotidien", msg)
        logger.info(f"[SCHEDULER] Récap quotidien envoyé: {nb_sent} emails, {nb_batches} batches")
        
    except Exception as e:
        logger.error(f"[SCHEDULER] send_daily_recap: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# RATTRAPAGE AU DÉMARRAGE
# ──────────────────────────────────────────────────────────────────────────────

def run_startup_catchup():
    """
    Vérifie les jobs manqués du jour et les rattrape immédiatement.
    Appelé une seule fois au démarrage de Flask.

    Règles :
      ≥ 07h45 et auto_plan non fait     → auto-planifie maintenant
      ≥ 08h00 et scrapings non lancés   → lance les scrapings planifiés
      ≥ 10h00 et emails matin non faits → envoie le lot matin
      ≥ 14h00 et emails après-midi non faits → envoie le lot après-midi
      ≥ 20h00 et pipeline non fait      → lance le pipeline
    """
    now  = datetime.now()
    hour = now.hour
    today = date.today().isoformat()

    logger.info(f"[CATCHUP] Démarrage à {now.strftime('%H:%M')} — vérification jobs manqués")

    # 1. Auto-planificateur (07h45)
    if hour >= 7 and not _job_ran_today('auto_plan'):
        logger.info("[CATCHUP] Auto-planificateur manqué → rattrapage")
        _run_auto_plan()

    # 2. Scrapings planifiés (08h00)
    # Condition : heure ≥ 8h ET il y a des campagnes 'planned' pour aujourd'hui
    if hour >= 8 and not _job_ran_today('planned_scrapings'):
        try:
            with get_conn() as conn:
                n = conn.execute(
                    "SELECT COUNT(*) as n FROM planned_campaigns WHERE date_planifiee=? AND statut='planned'",
                    (today,)
                ).fetchone()['n']
            if n > 0:
                logger.info(f"[CATCHUP] {n} scraping(s) manqué(s) → rattrapage")
                run_planned_scrapings()
            else:
                _log_job('planned_scrapings')  # rien à faire, marquer fait
        except Exception as e:
            logger.error(f"[CATCHUP] scrapings: {e}")

    # 3. Emails matin (10h00) — seulement si quota non atteint
    if hour >= 10 and not _job_ran_today('send_emails_morning'):
        logger.info("[CATCHUP] Emails matin manqués → rattrapage")
        send_morning_emails()

    # 4. Emails après-midi (14h00)
    if hour >= 14 and not _job_ran_today('send_emails_afternoon'):
        logger.info("[CATCHUP] Emails après-midi manqués → rattrapage")
        send_afternoon_emails()

    # 5. Pipeline soirée (20h00) — on ne le lance pas si PC allumé après minuit
    # (trop tard, les emails seraient envoyés le lendemain matin de toute façon)
    if 20 <= hour <= 23 and not _job_ran_today('evening_pipeline'):
        logger.info("[CATCHUP] Pipeline soirée manqué → rattrapage")
        import threading
        t = threading.Thread(target=run_pipeline, daemon=True)
        t.start()

    # 6. Blog IncidenX — rattrapage articles manqués
    # Article 08h
    if 8 <= hour < 12 and not _job_ran_today('blog_article_1'):
        logger.info("[CATCHUP] Article blog 08h manqué → rattrapage")
        threading.Thread(target=publish_blog_1, daemon=True).start()
    
    # Article 12h
    if 12 <= hour < 17 and not _job_ran_today('blog_article_2'):
        logger.info("[CATCHUP] Article blog 12h manqué → rattrapage")
        threading.Thread(target=publish_blog_2, daemon=True).start()
    
    # Article 17h
    if 17 <= hour <= 23 and not _job_ran_today('blog_article_3'):
        logger.info("[CATCHUP] Article blog 17h manqué → rattrapage")
        threading.Thread(target=publish_blog_3, daemon=True).start()

    # Fill check — toujours, peu importe l'heure
    logger.info("[CATCHUP] Fill check — vérification batches Resend")
    run_fill_check()

    logger.info("[CATCHUP] Vérification terminée.")


# ──────────────────────────────────────────────────────────────────────────────
# INIT
# ──────────────────────────────────────────────────────────────────────────────

def init_scheduler(app=None):
    """Initialise et démarre le scheduler. À appeler au démarrage Flask."""
    global _scheduler
    if _scheduler and _scheduler.running:
        return _scheduler

    _scheduler = BackgroundScheduler(timezone='Europe/Paris')

    # Auto-planificateur — 07h45
    _scheduler.add_job(
        _run_auto_plan,
        CronTrigger(hour=7, minute=45),
        id='auto_plan',
        replace_existing=True,
        misfire_grace_time=3600,  # tolère jusqu'à 1h de retard si PC vient de démarrer
    )

    # Scraping planifié — 08h00
    _scheduler.add_job(
        run_planned_scrapings,
        CronTrigger(hour=8, minute=0),
        id='planned_scrapings',
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Marquer les campagnes terminées — toutes les 30 min
    _scheduler.add_job(
        mark_planned_done,
        CronTrigger(minute='*/30'),
        id='mark_done',
        replace_existing=True,
    )

    # Fill check — toutes les 15 min : s'assure qu'il y a 4 batches Resend programmés
    _scheduler.add_job(
        run_fill_check,
        CronTrigger(minute='*/15'),
        id='fill_check',
        replace_existing=True,
    )

    # Importer les fonctions d'auto-approval
    from pipeline import notify_new_audits, auto_approve_after_timeout

    # Notification nouveaux audits — toutes les 30 min
    _scheduler.add_job(
        notify_new_audits,
        CronTrigger(minute='*/30'),
        id='notify_new_audits',
        replace_existing=True,
    )

    # Auto-approbation après 5h — toutes les heures
    _scheduler.add_job(
        auto_approve_after_timeout,
        CronTrigger(minute=0),
        id='auto_approve',
        replace_existing=True,
    )

    # Validation emails — toutes les 30 min
    def _validate_emails_job():
        try:
            from utils.email_validator import validate_pending_leads
            stats = validate_pending_leads(limit=50)
            logger.info(f"[SCHEDULER] Validation emails: {stats}")
        except Exception as e:
            logger.error(f"[SCHEDULER] validate_emails: {e}")

    _scheduler.add_job(
        _validate_emails_job,
        CronTrigger(minute='*/30'),
        id='validate_emails',
        replace_existing=True,
    )

    # Séquenceur de relances — 11h00 chaque jour
    def _run_sequencer():
        try:
            from dashboard.sequencer import generate_followups
            follows = generate_followups()
            logger.info(f"[SCHEDULER] Séquenceur: {len(follows)} relances potentielles")
        except Exception as e:
            logger.error(f"[SCHEDULER] sequencer: {e}")

    _scheduler.add_job(
        _run_sequencer,
        CronTrigger(hour=11, minute=0),
        id='run_sequencer',
        replace_existing=True,
    )

    # DEPRECATED — les envois passent par Resend scheduled batches
    # _scheduler.add_job(
    #     send_morning_emails,
    #     CronTrigger(hour=10, minute=0),
    #     id='send_emails_morning',
    #     replace_existing=True,
    #     misfire_grace_time=3600,
    # )
    # _scheduler.add_job(
    #     send_afternoon_emails,
    #     CronTrigger(hour=14, minute=0),
    #     id='send_emails_afternoon',
    #     replace_existing=True,
    #     misfire_grace_time=3600,
    # )

    # Pipeline soirée — 20h00
    _scheduler.add_job(
        run_pipeline,
        CronTrigger(hour=20, minute=0),
        id='evening_pipeline',
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Récap quotidien — 20h00
    _scheduler.add_job(
        send_daily_recap,
        CronTrigger(hour=20, minute=0),
        id='daily_recap',
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Blog IncidenX — publication échelonnée
    _scheduler.add_job(
        publish_blog_1,
        CronTrigger(hour=8, minute=0),
        id='blog_article_1',
        replace_existing=True,
        misfire_grace_time=7200,
    )

    _scheduler.add_job(
        publish_blog_2,
        CronTrigger(hour=12, minute=0),
        id='blog_article_2',
        replace_existing=True,
        misfire_grace_time=7200,
    )

    _scheduler.add_job(
        publish_blog_3,
        CronTrigger(hour=17, minute=0),
        id='blog_article_3',
        replace_existing=True,
        misfire_grace_time=7200,
    )

    _scheduler.start()
    logger.info("[SCHEDULER] Démarré (scraping 08h, emails 10h+14h, pipeline 20h, blog 08h+12h+17h)")

    # Rattrapage des jobs manqués
    import threading
    t = threading.Thread(target=run_startup_catchup, daemon=True)
    t.start()

    # Démarrer le scraper en arrière-plan
    from pipeline import start_background_scraper
    start_background_scraper()

    # Importer les fonctions d'auto-approval et notification
    from pipeline import notify_new_audits, auto_approve_after_timeout

    return _scheduler


def get_scheduler():
    return _scheduler


if __name__ == '__main__':
    import time
    logging.basicConfig(level=logging.INFO)
    
    print("[SCHEDULER] Démarrage du planificateur...")
    scheduler = init_scheduler()
    
    if scheduler:
        print("[OK] Scheduler actif - Ctrl+C pour arrêter")
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            print("\n[INFO] Arrêt demandé")
            scheduler.shutdown()
    else:
        print("[ERROR] Échec du démarrage")
        sys.exit(1)
