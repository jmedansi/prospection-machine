# -*- coding: utf-8 -*-
"""
database/repos/campaigns_repo.py — Repository campagnes
"""
from __future__ import annotations
from database.connection import get_conn, logger


class CampaignsRepo:

    def get_all(self, date_start: str | None = None, date_end: str | None = None) -> list[dict]:
        """Liste toutes les campagnes avec leurs stats agrégées."""
        try:
            where, params = "WHERE 1=1", []
            if date_start:
                where += " AND date(c.date_creation) >= ?"
                params.append(date_start)
            if date_end:
                where += " AND date(c.date_creation) <= ?"
                params.append(date_end)
            with get_conn() as conn:
                rows = conn.execute(f"""
                    SELECT
                        c.*,
                        (SELECT COUNT(*) FROM leads_bruts WHERE campaign_id=c.id)                                                  AS leads_total,
                        (SELECT COUNT(*) FROM leads_bruts WHERE campaign_id=c.id AND site_web IS NOT NULL AND site_web!='')         AS leads_avec_site,
                        (SELECT COUNT(*) FROM leads_bruts WHERE campaign_id=c.id AND email IS NOT NULL AND email!='')               AS leads_avec_email,
                        (SELECT COUNT(*) FROM leads_bruts WHERE campaign_id=c.id AND statut IN ('audite','email_genere','envoye'))  AS nb_audites,
                        (SELECT COUNT(*) FROM emails_envoyes ee JOIN leads_bruts lb ON ee.lead_id=lb.id WHERE lb.campaign_id=c.id)  AS emails_envoyes,
                        (SELECT COUNT(*) FROM emails_envoyes ee JOIN leads_bruts lb ON ee.lead_id=lb.id WHERE lb.campaign_id=c.id AND ee.ouvert=1)  AS nb_ouverts,
                        (SELECT COUNT(*) FROM emails_envoyes ee JOIN leads_bruts lb ON ee.lead_id=lb.id WHERE lb.campaign_id=c.id AND ee.repondu=1) AS nb_reponses
                    FROM campagnes c
                    {where}
                    ORDER BY c.date_creation DESC
                    LIMIT 100
                """, params).fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"CampaignsRepo.get_all → {e}")
            return []

    def get_by_id(self, camp_id: int) -> dict | None:
        try:
            with get_conn() as conn:
                row = conn.execute(
                    "SELECT * FROM campagnes WHERE id=?", (camp_id,)
                ).fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"CampaignsRepo.get_by_id({camp_id}) → {e}")
            return None

    def create(self, nom: str, secteur: str = "", ville: str = "",
               nb_demande: int = 0) -> int | None:
        try:
            with get_conn() as conn:
                cur = conn.execute("""
                    INSERT INTO campagnes (nom, secteur, ville, nb_demande)
                    VALUES (?, ?, ?, ?)
                """, (nom, secteur, ville, nb_demande))
                conn.commit()
                return cur.lastrowid
        except Exception as e:
            logger.error(f"CampaignsRepo.create({nom}) → {e}")
            return None

    def delete(self, camp_id: int) -> bool:
        try:
            with get_conn() as conn:
                conn.execute("DELETE FROM campagnes WHERE id=?", (camp_id,))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"CampaignsRepo.delete({camp_id}) → {e}")
            return False


campaigns_repo = CampaignsRepo()
