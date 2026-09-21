# -*- coding: utf-8 -*-
"""
services/task_worker.py — Gestionnaire de tâches en arrière-plan
Découple les opérations lourdes (LinkedIn, Emails) de l'event loop Flask.
"""

import threading
import queue
import logging
import time
import uuid
from typing import Dict, Any, Optional, Callable
from datetime import datetime

logger = logging.getLogger(__name__)

# État des tâches : { "task_id": { "status": "pending"|"running"|"done"|"failed", "progress": 0-100, "result": {}, "error": None } }
_tasks: Dict[str, Dict[str, Any]] = {}
_task_queue = queue.Queue()
_worker_thread: Optional[threading.Thread] = None

def start_worker():
    """Démarre le thread de travail s'il n'est pas déjà actif."""
    global _worker_thread
    if _worker_thread is None or not _worker_thread.is_alive():
        _worker_thread = threading.Thread(target=_worker_loop, daemon=True, name="TaskWorker")
        _worker_thread.start()
        logger.info("[task_worker] Worker démarré")

def enqueue_task(func: Callable, args: tuple = (), kwargs: dict = {}, label: str = "Tâche") -> str:
    """Ajoute une tâche à la file d'attente et retourne son ID."""
    task_id = str(uuid.uuid4())[:8]
    _tasks[task_id] = {
        "id": task_id,
        "label": label,
        "status": "pending",
        "progress": 0,
        "started_at": datetime.now().isoformat(),
        "ended_at": None,
        "result": None,
        "error": None
    }
    _task_queue.put((task_id, func, args, kwargs))
    start_worker()
    logger.info(f"[task_worker] Tâche {task_id} enfilée : {label}")
    return task_id

def get_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    """Retourne l'état courant d'une tâche."""
    return _tasks.get(task_id)

def list_active_tasks() -> list:
    """Liste toutes les tâches récentes (non 'done' ou 'failed' ou terminées depuis peu)."""
    # On pourrait nettoyer les vieilles tâches ici
    return list(_tasks.values())

def _worker_loop():
    """Boucle principale du thread de travail."""
    while True:
        try:
            task_id, func, args, kwargs = _task_queue.get()
            task = _tasks[task_id]
            task["status"] = "running"
            task["progress"] = 10
            
            logger.info(f"[task_worker] Exécution tâche {task_id} ({task['label']})")
            
            try:
                # Exécution de la fonction
                result = func(*args, **kwargs)
                task["status"] = "done"
                task["progress"] = 100
                task["result"] = result
            except Exception as e:
                logger.error(f"[task_worker] Échec tâche {task_id} : {e}", exc_info=True)
                task["status"] = "failed"
                task["error"] = str(e)
            finally:
                task["ended_at"] = datetime.now().isoformat()
                _task_queue.task_done()
                
        except Exception as e:
            logger.error(f"[task_worker] Erreur critique dans la boucle worker : {e}")
            time.sleep(1)

# --- Fonctions utilitaires pour les tâches courantes ---

def task_generate_emails(campaign_id: Optional[int] = None, limit: int = 100):
    """Wrapper pour la génération d'emails Sniper."""
    from sniper.email_generator import generate_sniper_emails_batch
    return generate_sniper_emails_batch(campaign_id=campaign_id, limit=limit)

def task_linkedin_outreach(audit_id: int, lead_id: int, prenom: str, nom: str, company_name: str, domain: str, site_web: str):
    """Wrapper pour l'outreach LinkedIn."""
    from sniper.linkedin_agent import send_linkedin_outreach
    return send_linkedin_outreach(
        audit_id=audit_id, lead_id=lead_id,
        prenom=prenom, nom=nom,
        company_name=company_name, domain=domain, site_web=site_web
    )
