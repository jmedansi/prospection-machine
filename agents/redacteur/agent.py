# -*- coding: utf-8 -*-
"""
agents/redacteur/agent.py — RédacteurAgent

Responsabilité unique : générer le contenu personnalisé de l'email
(objet + corps HTML) à partir des données d'audit d'un lead.

Entrée  : lead_id (int) ou liste lead_ids[]
Sortie  : AgentResult { lead_id, email_objet, profile, success_count }
"""
from __future__ import annotations
import time
from core.result import BaseAgent, AgentResult, timed
from database.repos import leads_repo, audits_repo


class RedacteurAgent(BaseAgent):
    name = "redacteur"

    @timed("redacteur")
    def run(self, lead_ids: list[int]) -> AgentResult:
        """
        Génère les emails pour une liste de leads.

        Args:
            lead_ids: Liste d'IDs de leads audités

        Returns:
            AgentResult.data = { "success_count": int, "errors": list }
        """
        if not lead_ids:
            return self.fail("lead_ids est requis et ne peut pas être vide")

        from services.email_generator import generate_email_for_lead

        success_count, errors = 0, []

        for lead_id in lead_ids:
            try:
                ok = generate_email_for_lead(lead_id)
                if ok:
                    success_count += 1
                else:
                    errors.append({"lead_id": lead_id, "error": "génération échouée (données manquantes ?)"})
            except Exception as e:
                errors.append({"lead_id": lead_id, "error": str(e)})

        if success_count == 0 and errors:
            return self.fail(
                f"Aucun email généré. {len(errors)} erreur(s).",
                data={"errors": errors},
            )

        self.logger.info(f"Emails générés : {success_count}/{len(lead_ids)}")
        return self.ok({
            "success_count": success_count,
            "total":         len(lead_ids),
            "errors":        errors,
        })

    @timed("redacteur")
    def run_one(self, lead_id: int) -> AgentResult:
        """Génère l'email pour un seul lead."""
        result = self.run([lead_id])
        if result.success and result.data.get("success_count", 0) > 0:
            # Récupérer l'email généré pour le retourner
            lead = leads_repo.get_by_id(lead_id)
            return self.ok({
                "lead_id":     lead_id,
                "email_objet": lead.get("email_objet") if lead else None,
                "profile":     (lead.get("email_objet") or "").split(" - ")[0] if lead else None,
            })
        return result


redacteur_agent = RedacteurAgent()
