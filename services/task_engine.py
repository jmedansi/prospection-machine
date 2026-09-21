# -*- coding: utf-8 -*-
"""
services/task_engine.py — Moteur Unifié d'Exécution Asynchrone (Task Engine SaaS Ultra)

Fonctionnalités :
- Persistance complète dans la table SQLite `async_tasks`
- Pool d'exécution multi-threads résilient (ThreadPoolExecutor)
- Suivi de progression en temps réel (pourcentage, item courant, totaux)
- Capture et streaming des logs par tâche
- Diffusion temps réel via WebSocket (Flask-SocketIO)
- Support de l'annulation (cancellation tokens)
- Mécanisme de reprise sur panne au démarrage
"""
import os
import sys
import json
import time
import uuid
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, Optional, Callable, List

from core.config import ROOT, ensure_env
from database.connection import get_conn
from core.logger import get_logger

ensure_env()
logger = get_logger("task_engine", "app.log", level=logging.INFO)

# État d'annulation en mémoire pour réactivité instantanée
_CANCEL_FLAGS: Dict[str, bool] = {}

# Pool d'exécution centralisé
MAX_WORKERS = 4
_EXECUTOR = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="TaskWorker")


def _broadcast_event(event_name: str, data: Dict[str, Any]):
    """Émet un événement WebSocket vers tous les clients connectés."""
    try:
        from dashboard.app import socketio
        if socketio:
            socketio.emit(event_name, data)
    except Exception:
        pass


class TaskEngine:
    """Gestionnaire central des tâches asynchrones."""

    @staticmethod
    def submit_task(
        task_type: str,
        label: str,
        func: Callable,
        args: tuple = (),
        kwargs: Optional[dict] = None,
        total_items: int = 0
    ) -> str:
        """
        Enregistre et soumet une nouvelle tâche asynchrone au pool de workers.
        
        Args:
            task_type: Type de tâche (ex: 'scrape_maps', 'audit_batch', 'email_gen')
            label: Libellé lisible pour l'UI
            func: Fonction cible callable
            args: Arguments positionnels
            kwargs: Arguments nommés
            total_items: Nombre total d'éléments à traiter (si connu)
        
        Returns:
            task_id (str)
        """
        if kwargs is None:
            kwargs = {}

        task_id = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()
        params_str = json.dumps({"args": [str(a) for a in args], "kwargs": {k: str(v) for k, v in kwargs.items()}}, ensure_ascii=False)

        # 1. Persister dans SQLite
        try:
            with get_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO async_tasks (
                        id, task_type, label, status, progress, total_items, 
                        processed_items, params_json, created_at, logs_json
                    ) VALUES (?, ?, ?, 'pending', 0, ?, 0, ?, ?, '[]')
                    """,
                    (task_id, task_type, label, total_items, params_str, now)
                )
                conn.commit()
        except Exception as e:
            logger.error(f"[TaskEngine] Erreur insertion tâche {task_id}: {e}")

        _CANCEL_FLAGS[task_id] = False

        # 2. Diffuser l'événement de création
        _broadcast_event("task_created", {
            "id": task_id,
            "task_type": task_type,
            "label": label,
            "status": "pending",
            "progress": 0,
            "total_items": total_items,
            "created_at": now
        })

        # 3. Lancer dans le ThreadPoolExecutor
        _EXECUTOR.submit(TaskEngine._run_task_wrapper, task_id, func, args, kwargs)
        logger.info(f"[TaskEngine] Tâche {task_id} soumise : {label} ({task_type})")
        return task_id

    @staticmethod
    def _run_task_wrapper(task_id: str, func: Callable, args: tuple, kwargs: dict):
        """Wrapper d'exécution d'une tâche avec capture des métriques et des erreurs."""
        start_time = datetime.now().isoformat()

        # Marquer comme 'running'
        TaskEngine._update_db_status(task_id, status="running", started_at=start_time)
        TaskEngine.log(task_id, f"Démarrage de la tâche : {task_id}", level="info")
        _broadcast_event("task_update", {"id": task_id, "status": "running", "started_at": start_time})

        try:
            # Vérifier si déjà annulée
            if TaskEngine.is_cancelled(task_id):
                TaskEngine._mark_cancelled(task_id)
                return

            # Passer task_id en kwarg si la fonction accepte 'task_id'
            import inspect
            sig = inspect.signature(func)
            if "task_id" in sig.parameters:
                kwargs["task_id"] = task_id

            result = func(*args, **kwargs)

            # Vérifier si annulée pendant l'exécution
            if TaskEngine.is_cancelled(task_id):
                TaskEngine._mark_cancelled(task_id)
                return

            # Tâche complétée avec succès
            completed_time = datetime.now().isoformat()
            res_json = json.dumps(result if isinstance(result, (dict, list, str, int, bool)) else str(result), ensure_ascii=False)
            
            with get_conn() as conn:
                conn.execute(
                    """
                    UPDATE async_tasks 
                    SET status = 'completed', progress = 100, completed_at = ?, result_json = ?
                    WHERE id = ?
                    """,
                    (completed_time, res_json, task_id)
                )
                conn.commit()

            TaskEngine.log(task_id, "Tâche terminée avec succès (100%)", level="info")
            _broadcast_event("task_completed", {
                "id": task_id,
                "status": "completed",
                "progress": 100,
                "completed_at": completed_time,
                "result": result
            })
            logger.info(f"[TaskEngine] Tâche {task_id} complétée avec succès")

        except Exception as e:
            error_msg = str(e)
            completed_time = datetime.now().isoformat()
            logger.error(f"[TaskEngine] Échec tâche {task_id}: {error_msg}", exc_info=True)

            with get_conn() as conn:
                conn.execute(
                    """
                    UPDATE async_tasks 
                    SET status = 'failed', completed_at = ?, error_message = ?
                    WHERE id = ?
                    """,
                    (completed_time, error_msg, task_id)
                )
                conn.commit()

            TaskEngine.log(task_id, f"Erreur critique : {error_msg}", level="error")
            _broadcast_event("task_completed", {
                "id": task_id,
                "status": "failed",
                "completed_at": completed_time,
                "error": error_msg
            })

    @staticmethod
    def update_progress(
        task_id: str,
        processed_items: int,
        total_items: Optional[int] = None,
        current_item_label: str = "",
        progress_pct: Optional[int] = None
    ):
        """Met à jour l'avancement d'une tâche."""
        try:
            with get_conn() as conn:
                if total_items is not None and total_items > 0:
                    calculated_pct = int((processed_items / total_items) * 100)
                    pct = progress_pct if progress_pct is not None else min(calculated_pct, 99)
                    conn.execute(
                        """
                        UPDATE async_tasks 
                        SET processed_items = ?, total_items = ?, current_item_label = ?, progress = ?
                        WHERE id = ?
                        """,
                        (processed_items, total_items, current_item_label, pct, task_id)
                    )
                else:
                    pct = progress_pct if progress_pct is not None else 0
                    conn.execute(
                        """
                        UPDATE async_tasks 
                        SET processed_items = ?, current_item_label = ?, progress = ?
                        WHERE id = ?
                        """,
                        (processed_items, current_item_label, pct, task_id)
                    )
                conn.commit()

            _broadcast_event("task_update", {
                "id": task_id,
                "status": "running",
                "processed_items": processed_items,
                "total_items": total_items,
                "current_item_label": current_item_label,
                "progress": pct
            })
        except Exception as e:
            logger.error(f"[TaskEngine] Erreur update_progress {task_id}: {e}")

    @staticmethod
    def log(task_id: str, message: str, level: str = "info"):
        """Ajoute une ligne de log horodatée à la tâche."""
        now_ts = datetime.now().strftime("%H:%M:%S")
        log_entry = {"time": now_ts, "level": level, "msg": message}

        try:
            with get_conn() as conn:
                row = conn.execute("SELECT logs_json FROM async_tasks WHERE id = ?", (task_id,)).fetchone()
                if row:
                    logs = json.loads(row[0]) if row[0] else []
                    logs.append(log_entry)
                    # Garder au maximum 200 logs par tâche
                    if len(logs) > 200:
                        logs = logs[-200:]
                    conn.execute("UPDATE async_tasks SET logs_json = ? WHERE id = ?", (json.dumps(logs, ensure_ascii=False), task_id))
                    conn.commit()

            _broadcast_event("task_log", {"id": task_id, "log": log_entry})
        except Exception as e:
            logger.error(f"[TaskEngine] Erreur append log {task_id}: {e}")

    @staticmethod
    def cancel_task(task_id: str) -> bool:
        """Demande l'annulation immédiate d'une tâche."""
        _CANCEL_FLAGS[task_id] = True
        TaskEngine._mark_cancelled(task_id)
        return True

    @staticmethod
    def is_cancelled(task_id: str) -> bool:
        """Vérifie si la tâche a reçu un signal d'annulation."""
        return _CANCEL_FLAGS.get(task_id, False)

    @staticmethod
    def _mark_cancelled(task_id: str):
        """Passe la tâche en statut cancelled."""
        now = datetime.now().isoformat()
        try:
            with get_conn() as conn:
                conn.execute(
                    "UPDATE async_tasks SET status = 'cancelled', completed_at = ? WHERE id = ?",
                    (now, task_id)
                )
                conn.commit()
            TaskEngine.log(task_id, "Tâche annulée par l'utilisateur", level="warning")
            _broadcast_event("task_completed", {"id": task_id, "status": "cancelled", "completed_at": now})
            logger.warning(f"[TaskEngine] Tâche {task_id} annulée")
        except Exception as e:
            logger.error(f"[TaskEngine] Erreur mark_cancelled {task_id}: {e}")

    @staticmethod
    def _update_db_status(task_id: str, status: str, started_at: Optional[str] = None):
        try:
            with get_conn() as conn:
                if started_at:
                    conn.execute("UPDATE async_tasks SET status = ?, started_at = ? WHERE id = ?", (status, started_at, task_id))
                else:
                    conn.execute("UPDATE async_tasks SET status = ? WHERE id = ?", (status, task_id))
                conn.commit()
        except Exception as e:
            logger.error(f"[TaskEngine] Erreur update_db_status {task_id}: {e}")

    @staticmethod
    def get_task(task_id: str) -> Optional[Dict[str, Any]]:
        """Récupère les détails d'une tâche."""
        try:
            with get_conn() as conn:
                conn.row_factory = sqlite3_row_factory
                row = conn.execute("SELECT * FROM async_tasks WHERE id = ?", (task_id,)).fetchone()
                if row:
                    data = dict(row)
                    data["logs"] = json.loads(data.get("logs_json") or "[]")
                    data["result"] = json.loads(data.get("result_json") or "{}")
                    data["params"] = json.loads(data.get("params_json") or "{}")
                    return data
        except Exception as e:
            logger.error(f"[TaskEngine] Erreur get_task {task_id}: {e}")
        return None

    @staticmethod
    def list_tasks(status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Liste les tâches récentes avec filtre optionnel."""
        try:
            with get_conn() as conn:
                conn.row_factory = sqlite3_row_factory
                if status:
                    rows = conn.execute(
                        "SELECT * FROM async_tasks WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                        (status, limit)
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM async_tasks ORDER BY created_at DESC LIMIT ?",
                        (limit,)
                    ).fetchall()

                result = []
                for r in rows:
                    item = dict(r)
                    item["logs"] = json.loads(item.get("logs_json") or "[]")
                    item["result"] = json.loads(item.get("result_json") or "{}")
                    result.append(item)
                return result
        except Exception as e:
            logger.error(f"[TaskEngine] Erreur list_tasks: {e}")
            return []


def sqlite3_row_factory(cursor, row):
    """Helper row factory pour convertir sqlite3.Row en dict propre."""
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d
