# -*- coding: utf-8 -*-
"""
agents/enrichisseur/agent.py — EnrichisseurAgent

Responsabilité unique : enrichir un lead avec des données manquantes
(email du CEO, validation email, téléphone, etc.).

Entrée  : lead_id (int)
Sortie  : AgentResult { lead_id, enriched_fields: dict }
"""
from __future__ import annotations
import threading
from core.result import BaseAgent, AgentResult, timed
from database.repos import leads_repo
from services.job_tracker import _enrich_job, reset_enrich_job


class EnrichisseurAgent(BaseAgent):
    name = "enrichisseur"

    @timed("enrichisseur")
    def run(self, lead_id: int | None = None, lead_ids: list[int] | None = None) -> AgentResult:
        """
        Enrichit un ou plusieurs leads avec email CEO / validation.
        """
        if lead_ids:
            if _enrich_job.get("running"):
                return self.fail("Une recherche d'emails est déjà en cours", error_type="ConflictError")
            
            total = len(lead_ids)
            reset_enrich_job(total=total)

            def _run_bulk():
                try:
                    for lid in lead_ids:
                        if not _enrich_job["running"]: break
                        try:
                            res = self._enrich_single(lid)
                            if res.success and res.data.get("enriched_fields"):
                                _enrich_job["success"] += 1
                                _enrich_job["results"].append({"id": lid, "status": "success", "found": list(res.data["enriched_fields"].keys())})
                            else:
                                _enrich_job["failed"] += 1
                                _enrich_job["results"].append({"id": lid, "status": "no_new_data"})
                        except Exception as e:
                            _enrich_job["failed"] += 1
                            _enrich_job["results"].append({"id": lid, "status": "error", "error": str(e)})
                        _enrich_job["current"] += 1
                finally:
                    _enrich_job["running"] = False

                self.logger.info(f"Recherche emails terminée : {_enrich_job['success']} trouvés sur {total}")

            threading.Thread(target=_run_bulk, daemon=True).start()
            return self.ok({"message": "Recherche lancée", "total": total})

        elif lead_id:
            return self._enrich_single(lead_id)
        
        return self.fail("lead_id ou lead_ids requis")

    def _enrich_single(self, lead_id: int) -> AgentResult:
        lead = leads_repo.get_by_id(lead_id)
        if not lead:
            return self.fail(f"Lead {lead_id} introuvable", error_type="NotFoundError")

        enriched = {}
        site_web = lead.get("site_web", "")
        if site_web and not lead.get("email_valide"):
            try:
                from core.contact_finder import find_contacts
                contacts = find_contacts(site_web, lead.get("nom", ""))
                fields = {k: v for k, v in contacts.items() if v is not None}
                if fields:
                    enriched.update(fields)
                    leads_repo.update_fields(lead_id, fields)
            except Exception as e:
                self.logger.warning(f"contact_finder échoué pour lead {lead_id}: {e}")

        return self.ok({"lead_id": lead_id, "enriched_fields": enriched})

    def status(self) -> dict:
        """Retourne l'état courant du job d'enrichissement."""
        return _enrich_job

    def stop(self):
        """Arrête la recherche d'emails en cours."""
        _enrich_job["running"] = False
        return True


enrichisseur_agent = EnrichisseurAgent()
