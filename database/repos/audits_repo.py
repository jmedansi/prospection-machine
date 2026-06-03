# -*- coding: utf-8 -*-
"""
database/repos/audits_repo.py — Repository leads_audites

Accès CRUD à la table leads_audites.
"""
from __future__ import annotations
from database.connection import get_conn, logger


class AuditsRepo:

    def get_by_lead_id(self, lead_id: int) -> dict | None:
        """Retourne l'audit complet d'un lead."""
        try:
            with get_conn() as conn:
                row = conn.execute(
                    "SELECT * FROM leads_audites WHERE lead_id=? LIMIT 1", (lead_id,)
                ).fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"AuditsRepo.get_by_lead_id({lead_id}) → {e}")
            return None

    def get_ready_for_email(self) -> list[dict]:
        """Leads audités avec email généré, non encore envoyés."""
        try:
            with get_conn() as conn:
                rows = conn.execute("""
                    SELECT
                        lb.id AS lead_id, lb.nom, lb.email, lb.ville,
                        lb.category, lb.site_web, lb.rating, lb.nb_avis,
                        la.score_performance, la.score_seo, la.score_urgence,
                        la.lcp_ms, la.email_objet, la.email_corps,
                        la.approuve, la.lien_rapport, la.lien_pdf,
                        la.probleme_principal
                    FROM leads_audites la
                    JOIN leads_bruts lb ON lb.id = la.lead_id
                    WHERE la.email_corps IS NOT NULL AND la.email_corps != ''
                      AND lb.email IS NOT NULL AND lb.email != ''
                      AND lb.statut NOT IN ('envoye', 'repondu', 'archive')
                    ORDER BY la.score_urgence DESC
                """).fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"AuditsRepo.get_ready_for_email → {e}")
            return []

    def get_with_local_report(self) -> list[dict]:
        """Leads avec un rapport local (lien_rapport = local://...)."""
        try:
            with get_conn() as conn:
                rows = conn.execute("""
                    SELECT lb.id, lb.nom, lb.ville, la.lien_rapport, la.score_urgence
                    FROM leads_audites la
                    JOIN leads_bruts lb ON lb.id = la.lead_id
                    WHERE la.lien_rapport LIKE 'local://%'
                    ORDER BY la.score_urgence DESC
                """).fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"AuditsRepo.get_with_local_report → {e}")
            return []

    def update_email_content(self, lead_id: int, objet: str, corps: str,
                              approuve: bool = False) -> bool:
        """Met à jour le contenu email d'un audit."""
        try:
            with get_conn() as conn:
                cur = conn.execute("""
                    UPDATE leads_audites
                    SET email_objet=?, email_corps=?, approuve=?
                    WHERE lead_id=?
                """, (objet, corps, int(approuve), lead_id))
                conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            logger.error(f"AuditsRepo.update_email_content({lead_id}) → {e}")
            return False

    def update_rapport_url(self, lead_id: int, url: str) -> bool:
        """Met à jour l'URL publique du rapport."""
        try:
            with get_conn() as conn:
                cur = conn.execute(
                    "UPDATE leads_audites SET lien_rapport=? WHERE lead_id=?",
                    (url, lead_id)
                )
                conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            logger.error(f"AuditsRepo.update_rapport_url({lead_id}) → {e}")
            return False

    def set_approval(self, lead_id: int, approuve: bool) -> bool:
        """Approuve ou rejette un email."""
        try:
            with get_conn() as conn:
                cur = conn.execute(
                    "UPDATE leads_audites SET approuve=? WHERE lead_id=?",
                    (int(approuve), lead_id)
                )
                conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            logger.error(f"AuditsRepo.set_approval({lead_id}) → {e}")
            return False


audits_repo = AuditsRepo()
