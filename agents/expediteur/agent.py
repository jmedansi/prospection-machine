# -*- coding: utf-8 -*-
"""
agents/expediteur/agent.py — ExpéditeurAgent

Responsabilité unique : envoyer les emails approuvés via Resend
et enregistrer chaque envoi dans emails_envoyes.

Entrée  : lead_ids[] (optionnel — si None, envoie tous les approuvés)
Sortie  : AgentResult { success_count, failed_count, results[] }
"""
from __future__ import annotations
import threading
from core.result import BaseAgent, AgentResult, timed
from services.job_tracker import _email_job, reset_email_job


class ExpediteurAgent(BaseAgent):
    name = "expediteur"

    @timed("expediteur")
    def run(self, lead_ids: list[int] | None = None) -> AgentResult:
        """
        Lance l'envoi des emails approuvés en arrière-plan.

        Args:
            lead_ids: Liste d'IDs à envoyer (None = tous les approuvés)

        Returns:
            AgentResult.data = { "message": str, "total": int }
        """
        if _email_job.get("running"):
            return self.fail("Un envoi est déjà en cours", error_type="ConflictError")

        from database.repos import audits_repo
        from envoi.resend_sender import send_prospecting_email
        from database.repos import emails_repo

        candidats = audits_repo.get_ready_for_email()

        filtered = [
            l for l in candidats
            if l.get("approuve")
            and (lead_ids is None or str(l.get("lead_id")) in [str(x) for x in lead_ids])
        ]

        if not filtered:
            return self.fail("Aucun email approuvé à envoyer",
                             error_type="EmptyQueueError")

        reset_email_job(total=len(filtered))

        def _run():
            try:
                for lead in filtered:
                    _email_job["current"] += 1
                    nom          = lead.get("nom", "prospect")
                    email        = (lead.get("email") or "").strip()
                    email_objet  = (lead.get("email_objet") or "").strip()
                    email_corps  = (lead.get("email_corps") or "").strip()
                    lien         = (lead.get("lien_rapport") or lead.get("site_web") or
                                    "https://audit.incidenx.com")

                    if not email or not email_corps:
                        _email_job["failed"] += 1
                        _email_job["results"].append({
                            "nom": nom, "statut": "skip",
                            "raison": "Email ou corps manquant",
                        })
                        continue

                    html = email_corps
                    if not email_corps.strip().startswith("<"):
                        html = f"<!DOCTYPE html><html><body>{email_corps.replace(chr(10), '<br>')}</body></html>"

                    result = send_prospecting_email(
                        prospect_email=email, prospect_nom=nom,
                        email_objet=email_objet, email_corps=html,
                        lien_rapport=lien, dry_run=False,
                    )

                    if result.get("success"):
                        record_id = emails_repo.insert({
                            "lead_id":            lead.get("lead_id"),
                            "message_id_resend":  result.get("message_id", ""),
                            "email_destinataire": email,
                            "email_objet":        email_objet,
                            "email_corps":        html,
                            "lien_rapport":       lien,
                            "statut_envoi":       "envoye",
                        })
                        from database.repos import leads_repo
                        leads_repo.update_statut(lead["lead_id"], "envoye")
                        # Marquer step1_envoye pour que IMAP poller puisse détecter les réponses
                        try:
                            from database.connection import get_conn
                            with get_conn() as conn:
                                conn.execute(
                                    "UPDATE leads_audites SET statut_prospection='step1_envoye' WHERE lead_id=?",
                                    (lead.get("lead_id"),)
                                )
                                conn.commit()
                        except Exception:
                            pass
                        _email_job["success"] += 1
                        _email_job["results"].append({"nom": nom, "statut": "ok"})
                    else:
                        _email_job["failed"] += 1
                        _email_job["results"].append({
                            "nom": nom, "statut": "error",
                            "raison": result.get("erreur"),
                        })
            except Exception as e:
                self.logger.error(f"Erreur envoi batch: {e}")
            finally:
                _email_job["running"] = False

        threading.Thread(target=_run, daemon=True).start()
        self.logger.info(f"Envoi lancé — {len(filtered)} emails")
        return self.ok({"message": f"Envoi de {len(filtered)} emails lancé", "total": len(filtered)})

    def status(self) -> dict:
        """État courant du job d'envoi."""
        return {
            "running":  _email_job.get("running", False),
            "current":  _email_job.get("current", 0),
            "total":    _email_job.get("total", 0),
            "success":  _email_job.get("success", 0),
            "failed":   _email_job.get("failed", 0),
            "results":  _email_job.get("results", [])[-20:],
        }

    @timed("expediteur")
    def send_test(self, lead_id: int, to_email: str) -> AgentResult:
        """
        Envoie un email de test à une adresse spécifique.

        Args:
            lead_id:  Lead dont on veut envoyer le contenu
            to_email: Adresse de réception du test

        Returns:
            AgentResult.data = { "message_id": str }
        """
        from database.repos import leads_repo
        from envoi.resend_sender import send_prospecting_email

        lead = leads_repo.get_by_id(lead_id)
        if not lead:
            return self.fail(f"Lead {lead_id} introuvable", error_type="NotFoundError")

        email_corps = lead.get("email_corps")
        email_objet = lead.get("email_objet")

        if not email_corps:
            return self.fail("Pas d'email généré pour ce lead", error_type="MissingDataError")

        result = send_prospecting_email(
            prospect_email=to_email,
            prospect_nom=lead.get("nom", "Test"),
            email_objet=f"[TEST] {email_objet or 'Email de test'}",
            email_corps=email_corps,
            lien_rapport=lead.get("lien_rapport", ""),
            dry_run=False,
        )

        if result.get("success"):
            return self.ok({"message_id": result.get("message_id"), "to": to_email})
        return self.fail(result.get("erreur", "Envoi test échoué"), error_type="SendError")


expediteur_agent = ExpediteurAgent()
