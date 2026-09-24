# -*- coding: utf-8 -*-
"""
agents/expediteur/agent.py — ExpéditeurAgent (PURGE V1 DÉFINITIVE)

⚠️ STUB DE COMPATIBILITÉ — ce module ne lit plus leads_audites et ne lance plus
d'envoi batch. Il est conservé UNIQUEMENT parce que la coquille V5 (archive)
charge encore `agents/` au démarrage.

PURGE V1 DÉFINITIVE : tout envoi RÉEL (initial ou relance) passe par le tunnel
v2 — `sequence_engine.send_initial` / `send_relance` → `gateway.envoyer` —
déclenché par l'utilisateur depuis le dashboard :
    - bouton « ▶ Envoyer » d'une campagne  → POST /api/v2/campagnes/<id>/send
    - bouton panel « Envoyer le mail »     → POST /api/v2/leads/<id>/email/send
    - bouton « Envoyer » d'une liste       → POST /api/v2/listes/<id>/send
Aucune route legacy /api/email/send* n'émet plus quoi que ce soit :
`run()` échoue toujours avec un message explicite.

`send_test()` est conservé mais passe par `sequence_engine.prepare_initial`
(contenu FRAIS rédigé = source de vérité) puis `gateway.envoyer` avec
`no_quota=True` / `ignore_quota=True` (envoi réel vers soi-même, aucun quota
boîte consommé, aucune transition / event / insertion emails_envoyes).
"""
from __future__ import annotations
from core.result import BaseAgent, AgentResult, timed
from services.job_tracker import _email_job


class ExpediteurAgent(BaseAgent):
    name = "expediteur"

    @timed("expediteur")
    def run(self, lead_ids: list[int] | None = None) -> AgentResult:
        """
        STUB (purge V1) : l'envoi batch V1 est désactivé.

        Tous les envois passent par le tunnel v2 piloté par l'utilisateur
        (route /api/v2/*). Ce return échoue volontairement — aucun email ne
        peut partir par ce chemin legacy.
        """
        return self.fail(
            "ExpéditeurAgent V1 désactivé (purge V1 définitive) : utilisez le "
            "bouton « Envoyer » de la campagne / de la liste dans le dashboard "
            "(routes /api/v2/campagnes/<id>/send, /api/v2/listes/<id>/send).",
            error_type="V1Disabled",
        )

    def status(self) -> dict:
        """État courant du job d'envoi (V1 résiduel)."""
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
        Envoi de TEST via le tunnel v2 : contenu rédigé (source de vérité,
        relu à l'instant T) + `gateway.envoyer` avec `no_quota=True` /
        `ignore_quota=True` → envoi réel vers `to_email` (adresse de test,
        PAS le prospect) sans aucun quota boîte consommé, sans transition
        d'état ni event ni insertion emails_envoyes.

        Args:
            lead_id:  Prospect v2 dont on veut tester le contenu
            to_email: Adresse de réception du test (soi-même)

        Returns:
            AgentResult.data = { "message_id": str }
        """
        from database import prospects as prospects_repo
        from envoi import sequence_engine, gateway

        prospect = prospects_repo.get_prospect(lead_id)
        if not prospect:
            return self.fail(f"Prospect {lead_id} introuvable", error_type="NotFoundError")

        cid = prospect.get("campagne_id")
        prep = sequence_engine.prepare_initial(cid, lead_id, dry_run=True)
        if not prep.get("ok"):
            return self.fail(
                f"Aucun email prêt à tester pour le prospect {lead_id} : "
                f"{prep.get('raison') or prep.get('message') or 'contenu manquant'}",
                error_type="MissingDataError",
            )

        resp = gateway.envoyer({
            "to": to_email,
            "nom": prospect.get("entreprise") or prospect.get("nom") or "Test",
            "subject": "[TEST] %s" % prep["objet"],
            "corps": prep["corps"],
            "campagne_id": cid,
            "dry_run": False,
            "no_quota": True,
            "ignore_quota": True,
        }, boite=None)
        if resp.get("success"):
            return self.ok({"message_id": resp.get("message_id"), "to": to_email})
        return self.fail(resp.get("erreur") or resp.get("statut") or "Envoi test échoué",
                         error_type="SendError")


expediteur_agent = ExpediteurAgent()