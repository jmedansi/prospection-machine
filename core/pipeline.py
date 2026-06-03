# -*- coding: utf-8 -*-
"""
core/pipeline.py — Orchestrateur de séquences d'agents

Définit les pipelines standards et permet de les enchaîner de façon
traçable. Chaque étape est loguée avec son statut succès/échec.

Usage:
    from core.pipeline import Pipeline

    result = Pipeline("audit_complet") \\
        .step(auditeur_agent.run, lead_ids=[42]) \\
        .step(editeur_agent.run, lead_id=42) \\
        .step(publieur_agent.run, slugs=["mon-client"]) \\
        .run()
"""
from __future__ import annotations
import time
import logging
from dataclasses import dataclass, field
from typing import Callable, Any
from core.result import AgentResult

logger = logging.getLogger("core.pipeline")


@dataclass
class PipelineStep:
    fn:     Callable[..., AgentResult]
    args:   tuple
    kwargs: dict
    name:   str = ""


@dataclass
class PipelineResult:
    pipeline_name: str
    success:       bool
    steps:         list[dict] = field(default_factory=list)
    duration_ms:   int = 0
    stopped_at:    str | None = None   # nom de l'étape ayant échoué

    def to_dict(self) -> dict:
        return {
            "pipeline":    self.pipeline_name,
            "success":     self.success,
            "duration_ms": self.duration_ms,
            "stopped_at":  self.stopped_at,
            "steps":       self.steps,
        }


class Pipeline:
    """
    Enchaîne des agents de façon séquentielle.
    S'arrête automatiquement au premier échec (comportement configurable).
    """

    def __init__(self, name: str, stop_on_failure: bool = True):
        self.name             = name
        self.stop_on_failure  = stop_on_failure
        self._steps: list[PipelineStep] = []

    def step(self, fn: Callable[..., AgentResult],
             *args, **kwargs) -> "Pipeline":
        """Ajoute une étape au pipeline."""
        self._steps.append(PipelineStep(
            fn=fn, args=args, kwargs=kwargs,
            name=getattr(fn, "__name__", str(fn)),
        ))
        return self

    def run(self) -> PipelineResult:
        """Exécute toutes les étapes dans l'ordre."""
        t0 = time.monotonic()
        steps_log: list[dict] = []
        stopped_at = None
        pipeline_success = True

        logger.info(f"[{self.name}] Démarrage — {len(self._steps)} étape(s)")

        for step in self._steps:
            result: AgentResult = step.fn(*step.args, **step.kwargs)
            entry = {
                "step":        step.name,
                "agent":       result.agent,
                "success":     result.success,
                "duration_ms": result.duration_ms,
                "error":       result.error,
                "data":        result.data,
            }
            steps_log.append(entry)

            if result.success:
                logger.info(f"  ✓ {step.name} ({result.duration_ms}ms)")
            else:
                logger.error(f"  ✗ {step.name} — {result.error}")
                pipeline_success = False
                stopped_at = step.name
                if self.stop_on_failure:
                    break

        duration = int((time.monotonic() - t0) * 1000)
        final = PipelineResult(
            pipeline_name=self.name,
            success=pipeline_success,
            steps=steps_log,
            duration_ms=duration,
            stopped_at=stopped_at,
        )
        logger.info(
            f"[{self.name}] {'✓ Terminé' if pipeline_success else '✗ Échoué'} "
            f"({duration}ms) — stopped_at={stopped_at}"
        )
        return final


# ─────────────────────────────────────────────────────────────────────────────
# Pipelines préconfigurés
# ─────────────────────────────────────────────────────────────────────────────

def pipeline_audit_and_publish(lead_id: int) -> PipelineResult:
    """Audit → génération rapport → publication GitHub."""
    from agents.auditeur  import auditeur_agent
    from agents.editeur   import editeur_agent
    from agents.publieur  import publieur_agent

    # Étape 1 : lancer l'audit (asynchrone, retourne immédiatement)
    audit_result = auditeur_agent.run(lead_ids=[lead_id])
    if not audit_result:
        return PipelineResult("audit_and_publish", False,
                              steps=[audit_result.to_dict()],
                              stopped_at="auditeur")

    # Étape 2 : générer le rapport HTML local
    edit_result = editeur_agent.run(lead_id)
    if not edit_result:
        return PipelineResult("audit_and_publish", False,
                              steps=[audit_result.to_dict(), edit_result.to_dict()],
                              stopped_at="editeur")

    # Étape 3 : publier sur GitHub
    slug = edit_result.data.get("slug", "")
    pub_result = publieur_agent.run([slug]) if slug else AgentResult(
        success=False, agent="publieur", error="slug manquant après éditeur"
    )

    return PipelineResult(
        "audit_and_publish",
        success=pub_result.success,
        steps=[audit_result.to_dict(), edit_result.to_dict(), pub_result.to_dict()],
        stopped_at=None if pub_result.success else "publieur",
    )


def pipeline_email_complet(lead_id: int) -> PipelineResult:
    """Rédaction email → envoi."""
    from agents.redacteur  import redacteur_agent
    from agents.expediteur import expediteur_agent

    return (
        Pipeline("email_complet")
        .step(redacteur_agent.run,   lead_ids=[lead_id])
        .step(expediteur_agent.run,  lead_ids=[lead_id])
        .run()
    )
