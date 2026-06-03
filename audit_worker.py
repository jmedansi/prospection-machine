# -*- coding: utf-8 -*-
"""
audit_worker.py — worker to process file-based audit queue

Run this as a long-running process. It will limit concurrent audit subprocesses
and ensure orderly processing so the dashboard never runs the auditeur in-process.

Config via env:
  AUDIT_WORKER_MAX_CONCURRENCY (default 2)
  AUDIT_POLL_S (default 2)

"""
import os
import sys
import time
import re
import unicodedata
import subprocess
import threading
import signal
import logging
from audit_queue import list_pending, claim_task, read_task, mark_done, PENDING
from services.job_tracker import _audit_job, reset_audit_job

ROOT = os.path.dirname(os.path.abspath(__file__))
MAX_CONCURRENCY = int(os.getenv('AUDIT_WORKER_MAX_CONCURRENCY', '2'))
POLL_S = float(os.getenv('AUDIT_POLL_S', '2.0'))

logger = logging.getLogger('audit_worker')
logger.setLevel(logging.INFO)
handler = logging.FileHandler(os.path.join(ROOT, 'audit_worker.log'))
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

_stop = False
_children = {}
_lock = threading.Lock()


def _strip_accents(s: str) -> str:
    """Supprime les accents pour un matching fiable des logs."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', s)
        if unicodedata.category(c) != 'Mn'
    )


def _spawn(task_path: str):
    task = read_task(task_path)
    # Build command: use current python executable to inherit venv packages
    python_exe = os.getenv('PYTHON_EXECUTABLE') or sys.executable or 'python'
    cmd = [python_exe, '-u', os.path.join(ROOT, 'auditeur', 'main.py')]
    if task.get('lead_names'):
        cmd += ['--leads'] + task['lead_names']
    elif task.get('lead_ids'):
        cmd += ['--ids'] + [str(x) for x in task['lead_ids']]
    elif task.get('limit'):
        cmd += ['--limit', str(task['limit'])]

    logger.info(f"Spawning audit subprocess for {task_path}: {cmd}")

    # Reset job state in the shared memory tracker
    try:
        total = 0
        if task.get('lead_names'):
            total = len(task['lead_names'])
        elif task.get('lead_ids'):
            total = len(task['lead_ids'])
        elif task.get('limit'):
            total = int(task['limit'])
            
        reset_audit_job(total=total)
        _audit_job['logs'].append(f"Worker spawning {os.path.basename(task_path)}")
    except Exception as e:
        logger.error(f"Failed to reset audit job tracker: {e}")

    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')

    with _lock:
        _children[proc.pid] = {'proc': proc, 'task': task_path}

    # Start a background thread to continuously read child stdout so the pipe
    # never fills and blocks the subprocess. The thread will also mark the
    # task done when the process exits.
    def _reader_thread(p, tpath):
        try:
            for line in p.stdout:
                line_s = line.rstrip()
                try:
                    logger.info(f"[child {p.pid}] {line_s}")
                except Exception:
                    pass
                
                # Parse stdout and update _audit_job metrics
                try:
                    _audit_job['logs'].append(line_s)
                    ll = _strip_accents(line_s.lower())
                    if "leads" in ll and ("auditer" in ll or "a auditer" in ll):
                        m = re.search(r"(\d+) leads", ll)
                        if m:
                            val = int(m.group(1))
                            if val > _audit_job.get('total', 0):
                                _audit_job['total'] = val
                    
                    if "[sqlite] [ok]" in ll or "[ok] audit enregistre" in ll:
                        _audit_job['current'] = _audit_job.get('current', 0) + 1
                    elif "[sqlite] [error]" in ll or "echoue" in ll or "failed" in ll:
                        _audit_job['failed'] = _audit_job.get('failed', 0) + 1
                        _audit_job['current'] = _audit_job.get('current', 0) + 1
                        
                    # Emit websocket event for real-time dashboard UI
                    try:
                        from dashboard.app import socketio
                        socketio.emit('audit_status', _audit_job)
                    except Exception as e:
                        pass
                except Exception as e:
                    logger.error(f"Error parsing child output line: {e}")
            
            # ensure process finished
            rc = p.wait()
            logger.info(f"Child {p.pid} exited (rc={rc}) for {tpath}")
            try:
                mark_done(tpath, {'returncode': rc})
            except Exception as e:
                logger.error(f"Failed to mark_done for {tpath}: {e}")
        except Exception:
            logger.exception(f"Reader thread for {tpath} failed")
        finally:
            # If no more active children and no pending tasks, clear running flag
            with _lock:
                _children.pop(p.pid, None)
            try:
                with _lock:
                    still = len(_children)
                pending = len(list_pending())
                if still == 0 and pending == 0:
                    _audit_job['running'] = False
                    _audit_job['logs'].append('Worker idle')
                    try:
                        from dashboard.app import socketio
                        socketio.emit('audit_status', _audit_job)
                    except Exception:
                        pass
            except Exception:
                pass

    thr = threading.Thread(target=_reader_thread, args=(proc, task_path), daemon=True)
    thr.start()


def _reap_children():
    # Reader threads handle draining stdout, marking done and removing from
    # _children. This function can be used to log currently finished children
    # that weren't cleaned up yet (defensive), but normally there should be
    # nothing to do here.
    with _lock:
        for pid, info in list(_children.items()):
            proc = info['proc']
            if proc.poll() is not None:
                logger.info(f"Child {pid} finished (rc={proc.returncode}) — awaiting reader thread cleanup")


def _handle_sigterm(signum, frame):
    global _stop
    logger.info('Received shutdown signal')
    _stop = True
    with _lock:
        for pid, info in list(_children.items()):
            try:
                info['proc'].kill()
            except Exception:
                pass


def run_loop():
    try:
        signal.signal(signal.SIGINT, _handle_sigterm)
        signal.signal(signal.SIGTERM, _handle_sigterm)
    except ValueError:
        # Ignore if not in the main thread (e.g., when run inside the Flask background thread)
        pass

    logger.info('Worker started')
    try:
        while not _stop:
            # reap finished children
            _reap_children()

            with _lock:
                active = len(_children)

            # spawn new tasks while under concurrency limit
            if active < MAX_CONCURRENCY:
                pending = list_pending()
                if pending:
                    # claim first pending task
                    task_to_claim = pending[0]
                    try:
                        claimed = claim_task(task_to_claim)
                        _spawn(claimed)
                    except Exception as e:
                        logger.error(f"Failed to claim/spawn {task_to_claim}: {e}")
                        # if claim failed, skip and continue
                        time.sleep(POLL_S)
                        continue
                else:
                    time.sleep(POLL_S)
            else:
                time.sleep(POLL_S)
    finally:
        logger.info('Worker stopping — waiting for children')
        with _lock:
            for pid, info in list(_children.items()):
                try:
                    info['proc'].wait(timeout=5)
                except Exception:
                    try:
                        info['proc'].kill()
                    except Exception:
                        pass


if __name__ == '__main__':
    run_loop()
