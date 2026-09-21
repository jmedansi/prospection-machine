# -*- coding: utf-8 -*-
"""
audit_queue.py — simple file-based queue for audit tasks

Usage:
  from audit_queue import enqueue_audit
  enqueue_audit({'lead_ids':[1,2]})

Worker will pick files from `queue/` (JSON) and move them to `processing/` while running.
"""
import os
import json
import uuid
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
QUEUE_DIR = os.path.join(ROOT, 'audit_queue')
PENDING = os.path.join(QUEUE_DIR, 'pending')
PROCESSING = os.path.join(QUEUE_DIR, 'processing')
HISTORY = os.path.join(QUEUE_DIR, 'history')

for d in (PENDING, PROCESSING, HISTORY):
    os.makedirs(d, exist_ok=True)


def _make_filename(prefix: str = 'task') -> str:
    ts = datetime.utcnow().strftime('%Y%m%dT%H%M%S')
    return f"{ts}-{prefix}-{uuid.uuid4().hex}.json"


def enqueue_audit(payload: dict) -> str:
    """Write a new task file into pending and return filename."""
    fname = _make_filename('audit')
    tmp = os.path.join(PENDING, fname + '.tmp')
    final = os.path.join(PENDING, fname)
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, final)
    return final


def list_pending() -> list:
    return sorted([os.path.join(PENDING, p) for p in os.listdir(PENDING) if p.endswith('.json')])


def claim_task(path: str) -> str:
    """Move task from pending to processing atomically and return new path."""
    base = os.path.basename(path)
    dest = os.path.join(PROCESSING, base)
    os.replace(path, dest)
    return dest


def mark_done(processing_path: str, result: dict | None = None) -> str:
    base = os.path.basename(processing_path)
    dest = os.path.join(HISTORY, base)
    os.replace(processing_path, dest)
    if result is not None:
        try:
            with open(dest + '.result.json', 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False)
        except Exception:
            pass
    return dest


def read_task(path: str) -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)
