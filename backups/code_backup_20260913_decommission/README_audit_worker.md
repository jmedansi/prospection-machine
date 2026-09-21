Audit queue & worker
=====================

This workspace includes a simple file-based queue and a long-running worker to
process audit tasks in isolated subprocesses, preventing the dashboard from
running the auditeur in-process (which caused Playwright/greenlet thread issues).

Files
- `audit_queue.py`: enqueue/read/claim/mark_done helpers using `audit_queue/pending`, `processing`, `history`.
- `audit_worker.py`: long-running worker; respects `AUDIT_WORKER_MAX_CONCURRENCY` env var; logs to `audit_worker.log`.
- `dashboard/routes/audits.py`: now enqueues tasks instead of launching the auditeur directly.

Run

Start the worker in a persistent terminal:

```bash
cd prospection-machine
python audit_worker.py
```

Enqueue an audit (via dashboard or curl):

```bash
curl -X POST http://localhost:5000/api/audit/launch -H "Content-Type: application/json" -d '{"limit":5}'
```

Notes
- This is intentionally simple and file-based for portability. For production
  consider Redis/RQ, RabbitMQ/Celery or a lightweight DB-backed queue.
- The worker spawns `auditeur/main.py` as an isolated process; a next step is to
  refactor `auditeur` to use a shared `BrowserManager` pool if you want in-process
  integration with better resource sharing.
