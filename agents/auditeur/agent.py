# -*- coding: utf-8 -*-
"""
agents/auditeur/agent.py — AuditeurAgent

Responsabilité unique : lancer l'analyse technique d'un ou plusieurs leads
(PageSpeed, SEO, GMB) et stocker les résultats dans leads_audites.

Entrée  : lead_ids[], lead_names[], limit
Sortie  : AgentResult { message, total }
"""
from __future__ import annotations
import os, sys, re, subprocess, threading, unicodedata
from core.result import BaseAgent, AgentResult, timed
from services.job_tracker import _audit_job, reset_audit_job

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _strip_accents(s: str) -> str:
    """Supprime les accents pour un matching fiable des logs."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', s)
        if unicodedata.category(c) != 'Mn'
    )


class AuditeurAgent(BaseAgent):
    name = "auditeur"
    _proc: subprocess.Popen | None = None

    @timed("auditeur")
    def run(self, lead_ids: list[int] | None = None,
            lead_names: list[str] | None = None,
            limit: int | None = None) -> AgentResult:
        """
        Lance l'audit en arrière-plan (subprocess auditeur/main.py).

        Au moins un paramètre parmi lead_ids, lead_names, limit est requis.

        Returns:
            AgentResult.data = { "message": str, "total": int }
        """
        if _audit_job.get("running"):
            return self.fail("Un audit est déjà en cours", error_type="ConflictError")

        if not lead_ids and not lead_names and not limit:
            return self.fail("lead_ids, lead_names ou limit requis")

        cmd = [sys.executable, "-u", os.path.join(ROOT, "auditeur", "main.py")]
        total = 0

        if lead_names:
            total = len(lead_names)
            cmd += ["--leads"] + lead_names
        elif lead_ids:
            total = len(lead_ids)
            cmd += ["--ids"] + [str(x) for x in lead_ids]
        elif limit:
            total = limit
            cmd += ["--limit", str(limit)]

        reset_audit_job(total=total)

        def _run():
            try:
                self._proc = subprocess.Popen(
                    cmd, cwd=ROOT,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace",
                )
                for line in self._proc.stdout:
                    line_s = line.rstrip()
                    _audit_job["logs"].append(line_s)
                    ll = _strip_accents(line_s.lower())
                    if "leads" in ll and ("auditer" in ll or "a auditer" in ll):
                        m = re.search(r"(\d+) leads", ll)
                        if m and int(m.group(1)) > _audit_job["total"]:
                            _audit_job["total"] = int(m.group(1))
                    # Patterns alignés avec audit_worker.py
                    if "[sqlite] [ok]" in ll or "[ok] audit enregistre" in ll:
                        _audit_job["current"] += 1
                    elif "[sqlite] [error]" in ll or ("echoue" in ll and "audit" in ll):
                        _audit_job["failed"] += 1
                        _audit_job["current"] += 1
                    # Diffusion WebSocket temps réel vers le dashboard
                    try:
                        from dashboard.app import socketio
                        socketio.emit('audit_status', dict(_audit_job))
                    except Exception:
                        pass
                self._proc.wait()
                _audit_job["returncode"] = self._proc.returncode
            except Exception as e:
                _audit_job["logs"].append(f"ERREUR: {e}")
                _audit_job["returncode"] = -1
            finally:
                _audit_job["running"] = False
                self._proc = None
                # Signal final de fin d'audit
                try:
                    from dashboard.app import socketio
                    socketio.emit('audit_status', dict(_audit_job))
                except Exception:
                    pass

        threading.Thread(target=_run, daemon=True).start()
        self.logger.info(f"Audit lancé — {total} leads")
        return self.ok({"message": "Audit lancé", "total": total})
    def status(self) -> dict:
        """Retourne l'état courant du job d'audit."""
        return {
            "running":    _audit_job.get("running", False),
            "current":    _audit_job.get("current", 0),
            "total":      _audit_job.get("total", 0),
            "failed":     _audit_job.get("failed", 0),
            "returncode": _audit_job.get("returncode"),
            "logs":       _audit_job.get("logs", [])[-20:],  # 20 dernières lignes
        }

    def stop(self):
        """Arrête le job d'audit en cours."""
        if self._proc:
            try:
                self._proc.kill() # Plus radical que terminate()
                self._proc.wait(timeout=2)
                self.logger.info("Audit job KILLED via API")
            except Exception as e:
                self.logger.error(f"Error killing audit job: {e}")
        _audit_job["running"] = False
        return True

auditeur_agent = AuditeurAgent()
