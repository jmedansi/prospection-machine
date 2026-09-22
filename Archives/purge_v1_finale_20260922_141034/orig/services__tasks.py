# -*- coding: utf-8 -*-
"""
services/tasks.py — Tâches Celery pour le pipeline asynchrone

Ce fichier définit les tâches atomiques pour remplacer les threading.Thread.
Celery gère automatiquement les retries et la résilience.
"""
from celery import Celery
import os
import sys

# Détection Redis disponible
REDIS_URL = os.environ.get("REDIS_URL")
USE_EAGER = False

if not REDIS_URL:
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, socket_timeout=2)
        r.ping()
    except:
        USE_EAGER = True

if USE_EAGER:
    print("[TASKS] Redis non disponible - mode EAGER (sync) activé")
    app = Celery("prospection", broker='memory://')
    app.conf.task_always_eager = True
    app.conf.task_eager_propagates = True
else:
    print(f"[TASKS] Redis activé: {REDIS_URL}")
    app = Celery("prospection", broker=REDIS_URL, backend=REDIS_URL)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_default_retry_delay=60,
    task_max_retries=3,
)


@app.task(bind=True, max_retries=3)
def task_scrape(self, campaign_id: int):
    """Lance le scraping pour une campagne donnée."""
    try:
        from services.scraper_runner import run_scraper_campaign
        run_scraper_campaign(campaign_id)
        return {"status": "completed", "campaign_id": campaign_id}
    except Exception as e:
        self.retry(exc=e, countdown=60)


@app.task(bind=True, max_retries=3)
def task_enrich(self, lead_id: int):
    """Enrichit un lead avec email et téléphone."""
    try:
        from agents.enrichisseur.agent import enrichisseur_agent
        result = enrichisseur_agent.run(lead_id=lead_id)
        return {"status": "completed", "lead_id": lead_id, "result": result}
    except Exception as e:
        self.retry(exc=e, countdown=60)


@app.task(bind=True, max_retries=3)
def task_audit(self, lead_id: int):
    """Lance l'audit technique pour un lead."""
    try:
        from agents.auditeur.agent import auditeur_agent
        result = auditeur_agent.run(lead_ids=[lead_id])
        return {"status": "completed", "lead_id": lead_id, "result": result}
    except Exception as e:
        self.retry(exc=e, countdown=60)


@app.task(bind=True, max_retries=3)
def task_generate_email(self, lead_id: int):
    """Génère l'email de prospection pour un lead audité."""
    try:
        from services.email_generator import generate_email_for_lead
        ok = generate_email_for_lead(lead_id)
        return {"status": "completed" if ok else "failed", "lead_id": lead_id}
    except Exception as e:
        self.retry(exc=e, countdown=60)


@app.task
def task_log_notification(notif_type: str, message: str, source: str = "system"):
    """Log une notification dans la table system_logs."""
    try:
        from database.db_manager import get_conn
        from datetime import datetime
        conn = get_conn()
        conn.execute(
            "INSERT INTO system_logs (type, message, source, created_at) VALUES (?, ?, ?, ?)",
            (notif_type, message, source, datetime.utcnow().isoformat())
        )
        conn.commit()
        return {"status": "logged"}
    except Exception as e:
        return {"status": "error", "message": str(e)}