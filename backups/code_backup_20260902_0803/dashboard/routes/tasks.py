# -*- coding: utf-8 -*-
"""
dashboard/routes/tasks.py — API Routes pour le Moteur de Tâches Asynchrones (Task Engine)
"""
from flask import Blueprint, jsonify, request
from services.task_engine import TaskEngine

tasks_bp = Blueprint('tasks', __name__)


@tasks_bp.route('/api/tasks', methods=['GET'])
def list_tasks_route():
    """Retourne la liste des tâches récentes."""
    status = request.args.get('status')
    limit = int(request.args.get('limit', 50))
    tasks = TaskEngine.list_tasks(status=status, limit=limit)
    return jsonify({"success": True, "tasks": tasks, "total": len(tasks)})


@tasks_bp.route('/api/tasks/<task_id>', methods=['GET'])
def get_task_route(task_id: str):
    """Retourne les détails et logs d'une tâche."""
    task = TaskEngine.get_task(task_id)
    if not task:
        return jsonify({"success": False, "error": "Tâche introuvable"}), 404
    return jsonify({"success": True, "task": task})


@tasks_bp.route('/api/tasks/<task_id>/cancel', methods=['POST'])
def cancel_task_route(task_id: str):
    """Annule une tâche en cours."""
    ok = TaskEngine.cancel_task(task_id)
    return jsonify({"success": ok, "message": f"Signal d'annulation envoyé pour {task_id}"})


@tasks_bp.route('/api/tasks/launch/<action>', methods=['POST'])
def launch_standard_task_route(action: str):
    """
    Lance une tâche standard via le TaskEngine.
    Actions supportées: 'audit_batch', 'email_generation', 'bodacc_scan'
    """
    from services.job_launcher import (
        launch_batch_audit, launch_batch_email_generation, launch_bodacc_scan
    )

    data = request.get_json(silent=True) or {}
    limit = int(data.get('limit', 25))

    if action == 'audit_batch':
        task_id = launch_batch_audit(limit=limit)
        return jsonify({"success": True, "task_id": task_id, "message": f"Audit de {limit} leads lancé"})
    elif action == 'email_generation':
        task_id = launch_batch_email_generation(limit=limit)
        return jsonify({"success": True, "task_id": task_id, "message": f"Génération de {limit} emails lancée"})
    elif action == 'bodacc_scan':
        task_id = launch_bodacc_scan(max_items=limit)
        return jsonify({"success": True, "task_id": task_id, "message": f"Scan BODACC ({limit} max) lancé"})
    else:
        return jsonify({"success": False, "error": f"Action inconnue: {action}"}), 400

