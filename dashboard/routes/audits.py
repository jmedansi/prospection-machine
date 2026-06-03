# -*- coding: utf-8 -*-
"""
dashboard/routes/audits.py — Routes API audits
"""
import os, re, shutil, sys, subprocess, threading
from flask import Blueprint, jsonify, request
from services.job_tracker import reset_audit_job, get_audit_status, _audit_job

audits_bp = Blueprint("audits", __name__)

# Process handle for the background audit subprocess (if any)
_audit_proc = None
_audit_proc_lock = threading.Lock()

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@audits_bp.route("/api/audit/launch", methods=["POST"])
def api_audit_launch():
    data = request.get_json() or {}
    lead_ids = data.get("lead_ids", [])
    lead_names = data.get("lead_names", [])
    limit = data.get("limit")

    # Previously we prevented concurrent launches here. We now enqueue tasks
    # and let the audit worker handle concurrency, so do not reject requests.

    # Enqueue the task for the audit worker
    from audit_queue import enqueue_audit

    payload = {}
    total = 1
    if lead_names:
        payload['lead_names'] = lead_names
        total = len(lead_names)
    elif lead_ids:
        payload['lead_ids'] = lead_ids
        total = len(lead_ids)
    elif limit:
        payload['limit'] = int(limit)
        total = int(limit)

    reset_audit_job(total=total)
    st = get_audit_status()
    print(f"[API] launch called. reset_audit_job run. running={st['running']} id={id(st)}")

    # persist task (worker will update job tracker when it starts processing)
    task_path = enqueue_audit(payload)
    return jsonify({'statut': 'enqueued', 'task': task_path}), 202


@audits_bp.route("/api/audit/retry-failed", methods=["POST"])
def api_audit_retry_failed():
    """Relance l'audit de tous les leads dont le statut est 'failed'."""
    try:
        from database import get_conn
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT lb.id FROM leads_bruts lb
                LEFT JOIN leads_audites la ON la.lead_id = lb.id
                WHERE lb.statut IN ('failed', 'audit_echoue')
                   OR (la.id IS NOT NULL AND la.score_performance = 0 AND la.template_used = 'failed')
            """).fetchall()
        ids = [r["id"] for r in rows]
        if not ids:
            return jsonify({"statut": "rien", "count": 0})

        # Reuse launch logic but inline for retry
        cmd = [sys.executable, "-u", os.path.join(ROOT, "auditeur", "main.py")]
        cmd += ["--ids"] + [str(x) for x in ids]
        reset_audit_job(total=len(ids))

        def _run_retry():
            global _audit_proc
            try:
                with _audit_proc_lock:
                    _audit_proc = subprocess.Popen(
                        cmd, cwd=ROOT,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, encoding='utf-8', errors='replace'
                    )
                for line in _audit_proc.stdout:
                    _audit_job['logs'].append(line.rstrip())
                _audit_proc.wait()
                _audit_job['returncode'] = _audit_proc.returncode
            except Exception as e:
                _audit_job['logs'].append(f'ERREUR: {e}')
                _audit_job['returncode'] = -1
            finally:
                _audit_job['running'] = False
                with _audit_proc_lock:
                    _audit_proc = None

        threading.Thread(target=_run_retry, daemon=True).start()
        return jsonify({"statut": "lance", "count": len(ids)}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@audits_bp.route("/api/audit/status")
def api_audit_status():
    st = get_audit_status()
    print(f"[API] status called. running={st['running']} id={id(st)}")
    return jsonify(st)


@audits_bp.route("/api/audit/stop", methods=["POST"])
def api_audit_stop():
    global _audit_proc
    with _audit_proc_lock:
        if _audit_proc:
            try:
                _audit_proc.kill()
                _audit_proc.wait(timeout=2)
            except Exception:
                pass
            _audit_proc = None
    _audit_job['running'] = False
    return jsonify({"success": True, "message": "Audit arrêté"})


@audits_bp.route("/api/audit/cleanup", methods=["POST"])
def api_audit_cleanup():
    """Supprime le rapport local et remet lien_rapport à NULL."""
    try:
        data    = request.get_json() or {}
        lead_id = data.get("lead_id")
        if not lead_id:
            return jsonify({"error": "lead_id requis"}), 400

        from database.repos import leads_repo, audits_repo
        lead = leads_repo.get_by_id(lead_id)
        if not lead:
            return jsonify({"error": "Lead non trouvé"}), 404

        nom  = lead.get("nom", "")
        slug = re.sub(r"[^a-z0-9\s]", "", nom.lower())
        slug = re.sub(r"\s+", "-", slug).strip("-")[:50]
        reports_dir = os.path.join(ROOT, "reporter", "reports")
        slug_dir    = os.path.join(reports_dir, slug)

        if os.path.isdir(slug_dir):
            shutil.rmtree(slug_dir)

        audits_repo.update_rapport_url(lead_id, "")
        return jsonify({"success": True, "lead_id": lead_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
