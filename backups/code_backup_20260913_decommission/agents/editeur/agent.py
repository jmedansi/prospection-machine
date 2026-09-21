# -*- coding: utf-8 -*-
"""
agents/editeur/agent.py — ÉditeurAgent

Responsabilité unique : générer le rapport HTML local pour un lead audité
et le sauvegarder dans reporter/reports/{slug}/.

Entrée  : lead_id (int)
Sortie  : AgentResult { lead_id, slug, local_path, local_url }
"""
from __future__ import annotations
import os
from core.result import BaseAgent, AgentResult, timed

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class EditeurAgent(BaseAgent):
    name = "editeur"

    @timed("editeur")
    def run(self, lead_id: int) -> AgentResult:
        """
        Génère le rapport HTML d'audit pour un lead.

        Le rapport est sauvegardé localement dans reporter/reports/{slug}/.
        L'URL locale est http://127.0.0.1:5001/previews/{slug}/

        Returns:
            AgentResult.data = { "lead_id", "slug", "local_path", "local_url" }
        """
        try:
            from reporter.main import run_report_for_lead
        except ImportError as e:
            return self.fail(f"Module reporter.main introuvable : {e}",
                             error_type="ImportError")

        try:
            result = run_report_for_lead(lead_id)
        except Exception as e:
            return self.fail(str(e), error_type=type(e).__name__)

        if not result:
            return self.fail(f"run_report_for_lead({lead_id}) a retourné None",
                             error_type="ReportError")

        slug      = result.get("slug", "")
        local_url = f"http://127.0.0.1:5001/previews/{slug}/"

        self.logger.info(f"Rapport généré : {slug}")
        return self.ok({
            "lead_id":    lead_id,
            "slug":       slug,
            "local_path": result.get("local_path", ""),
            "local_url":  local_url,
            "lien_rapport": result.get("lien_rapport", f"local://{slug}/"),
        })


editeur_agent = EditeurAgent()
