# -*- coding: utf-8 -*-
"""
agents/publieur/agent.py — PublieurAgent

Responsabilité unique : publier un ou plusieurs rapports locaux sur GitHub Pages
et mettre à jour le lien_rapport en base de données.

Entrée  : slugs[] (liste de slugs de rapports à publier)
Sortie  : AgentResult { published: [{slug, url}], failed: [{slug, error}] }
"""
from __future__ import annotations
import os
from core.result import BaseAgent, AgentResult, timed
from database.repos import audits_repo

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPORTS_DIR = os.path.join(ROOT, "reporter", "reports")


class PublieurAgent(BaseAgent):
    name = "publieur"

    @timed("publieur")
    def run(self, slugs: list[str]) -> AgentResult:
        """
        Publie les rapports locaux vers GitHub Pages.

        Args:
            slugs: Liste de slugs (noms de dossiers dans reporter/reports/)

        Returns:
            AgentResult.data = {
                "published": [{"slug": str, "url": str}],
                "failed":    [{"slug": str, "error": str}],
            }
        """
        if not slugs:
            return self.fail("slugs est requis et ne peut pas être vide")

        try:
            from dashboard.pipeline.report_publishing import publish_reports_batch
        except ImportError as e:
            return self.fail(f"Module report_publishing introuvable : {e}",
                             error_type="ImportError")

        published, failed = [], []

        for slug in slugs:
            slug_dir   = os.path.join(REPORTS_DIR, slug)
            index_path = os.path.join(slug_dir, "index.html")

            if not os.path.isdir(slug_dir):
                failed.append({"slug": slug, "error": f"Dossier introuvable : {slug_dir}"})
                continue
            if not os.path.isfile(index_path):
                failed.append({"slug": slug, "error": "index.html manquant dans le dossier"})
                continue

            try:
                url = publish_reports_batch([slug])
                if url:
                    published.append({"slug": slug, "url": url})
                    # Mettre à jour la DB si on trouve le lead via lien local
                    self._update_db_for_slug(slug, url)
                else:
                    failed.append({"slug": slug, "error": "publish_reports_batch n'a rien retourné"})
            except Exception as e:
                failed.append({"slug": slug, "error": str(e)})

        if not published and failed:
            return self.fail(
                f"Aucune publication réussie. {len(failed)} échec(s).",
                data={"published": published, "failed": failed},
            )

        self.logger.info(f"Publié : {len(published)}/{len(slugs)} rapports")
        return self.ok({"published": published, "failed": failed})

    def list_local(self) -> list[dict]:
        """Liste tous les rapports disponibles localement."""
        if not os.path.isdir(REPORTS_DIR):
            return []
        result = []
        for name in os.listdir(REPORTS_DIR):
            slug_dir = os.path.join(REPORTS_DIR, name)
            if os.path.isdir(slug_dir) and os.path.isfile(os.path.join(slug_dir, "index.html")):
                result.append({
                    "slug":      name,
                    "local":     True,
                    "local_url": f"http://127.0.0.1:5001/previews/{name}/",
                })
        return result

    @staticmethod
    def _update_db_for_slug(slug: str, public_url: str):
        """Met à jour lien_rapport en base pour le lead correspondant au slug."""
        try:
            from database.connection import get_conn
            with get_conn() as conn:
                row = conn.execute(
                    "SELECT lead_id FROM leads_audites WHERE lien_rapport LIKE ?",
                    (f"local://{slug}%",)
                ).fetchone()
                if row:
                    audits_repo.update_rapport_url(row["lead_id"], public_url)
                    conn.execute(
                        "UPDATE leads_bruts SET statut='audite' WHERE id=? AND statut='email_genere'",
                        (row["lead_id"],)
                    )
                    conn.commit()
        except Exception as e:
            import logging
            logging.getLogger("agents.publieur").warning(f"_update_db_for_slug({slug}): {e}")


publieur_agent = PublieurAgent()
