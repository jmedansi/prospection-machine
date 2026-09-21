# -*- coding: utf-8 -*-
"""
core/result.py — Contrat universel de retour pour tous les agents.

Chaque agent retourne toujours un AgentResult.
Jamais de None, jamais d'exception silencieuse.

Usage:
    from core.result import AgentResult, ok, fail

    def run(self, ...) -> AgentResult:
        try:
            ...
            return ok(self.name, {"lead_id": 42})
        except Exception as e:
            return fail(self.name, str(e))
"""

from __future__ import annotations
import time
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    """Résultat standardisé retourné par chaque agent."""
    success: bool
    agent: str                          # nom de l'agent ("auditeur", "expediteur", ...)
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None            # message d'erreur si success=False
    error_type: str | None = None       # classe d'erreur ("TimeoutError", "ValueError", ...)
    duration_ms: int = 0                # durée d'exécution mesurée par le décorateur

    # ------------------------------------------------------------------ helpers

    def raise_if_failed(self) -> "AgentResult":
        """Lève une RuntimeError si le résultat est un échec.
        Utile dans les pipelines séquentiels où on veut stopper à la première erreur."""
        if not self.success:
            raise RuntimeError(f"[{self.agent}] {self.error}")
        return self

    def to_dict(self) -> dict:
        return {
            "success":    self.success,
            "agent":      self.agent,
            "data":       self.data,
            "error":      self.error,
            "error_type": self.error_type,
            "duration_ms": self.duration_ms,
        }

    def __bool__(self) -> bool:
        return self.success

    def __repr__(self) -> str:
        if self.success:
            return f"<AgentResult ✓ {self.agent} ({self.duration_ms}ms)>"
        return f"<AgentResult ✗ {self.agent} — {self.error}>"


# ─────────────────────────────────────────────────────────────────────────────
# Constructeurs raccourcis
# ─────────────────────────────────────────────────────────────────────────────

def ok(agent: str, data: dict | None = None, duration_ms: int = 0) -> AgentResult:
    """Construit un AgentResult de succès."""
    result = AgentResult(success=True, agent=agent, data=data or {}, duration_ms=duration_ms)
    logger.debug(repr(result))
    return result


def fail(agent: str, error: str, error_type: str | None = None,
         data: dict | None = None, duration_ms: int = 0) -> AgentResult:
    """Construit un AgentResult d'échec."""
    result = AgentResult(
        success=False,
        agent=agent,
        data=data or {},
        error=error,
        error_type=error_type,
        duration_ms=duration_ms,
    )
    logger.warning(repr(result))
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Décorateur @timed — mesure la durée et gère les exceptions non attrapées
# ─────────────────────────────────────────────────────────────────────────────

def timed(agent_name: str):
    """
    Décorateur de méthode.
    - Mesure la durée d'exécution et l'injecte dans le AgentResult.
    - Attrape toute exception non gérée et la convertit en AgentResult d'échec.

    Usage:
        class MonAgent(BaseAgent):
            @timed("mon_agent")
            def run(self, ...) -> AgentResult:
                ...
    """
    def decorator(fn):
        def wrapper(*args, **kwargs) -> AgentResult:
            t0 = time.monotonic()
            try:
                result: AgentResult = fn(*args, **kwargs)
                result.duration_ms = int((time.monotonic() - t0) * 1000)
                return result
            except Exception as e:
                duration = int((time.monotonic() - t0) * 1000)
                logger.exception(f"[{agent_name}] Exception non gérée")
                return fail(
                    agent_name,
                    error=str(e),
                    error_type=type(e).__name__,
                    duration_ms=duration,
                )
        wrapper.__name__ = fn.__name__
        return wrapper
    return decorator


# ─────────────────────────────────────────────────────────────────────────────
# Classe de base pour tous les agents
# ─────────────────────────────────────────────────────────────────────────────

class BaseAgent:
    """
    Classe de base optionnelle pour les agents.
    Fournit self.name, self.logger, et les helpers ok()/fail().
    """
    name: str = "agent"

    def __init__(self):
        self.logger = logging.getLogger(f"agents.{self.name}")

    def ok(self, data: dict | None = None, duration_ms: int = 0) -> AgentResult:
        return ok(self.name, data, duration_ms)

    def fail(self, error: str, error_type: str | None = None,
             data: dict | None = None, duration_ms: int = 0) -> AgentResult:
        return fail(self.name, error, error_type, data, duration_ms)
