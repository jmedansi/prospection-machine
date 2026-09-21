# -*- coding: utf-8 -*-
from .connection import get_conn, logger


def insert_campaign(nom: str, secteur: str = "", ville: str = "", nb_demande: int = 0) -> int:
    """
    Cree une nouvelle campagne (LEGACY).
    Router vers create_campaign du campaign_tracker pour unifier.
    """
    from services.campaign_tracker import create_campaign
    return create_campaign(nom, secteur=secteur, ville=ville, source='maps', nb_demande=nb_demande)


def get_all_campaigns(date_start: str | None = None, date_end: str | None = None) -> list:
    """Retourne la liste de toutes les campagnes avec stats."""
    try:
        where_clause = "WHERE 1=1"
        params = []
        if date_start:
            where_clause += " AND date(c.date_creation) >= ?"
            params.append(date_start)
        if date_end:
            where_clause += " AND date(c.date_creation) <= ?"
            params.append(date_end)

        with get_conn() as conn:
            rows = conn.execute(f"""
                SELECT 
                    c.*,
                    (SELECT COUNT(*) FROM leads_bruts WHERE campaign_id = c.id) as leads_total,
                    (SELECT COUNT(*) FROM leads_bruts WHERE campaign_id = c.id AND site_web IS NOT NULL AND site_web != '') as leads_with_site,
                    (SELECT COUNT(*) FROM leads_bruts WHERE campaign_id = c.id AND email IS NOT NULL AND email != '') as leads_with_email,
                    (SELECT COUNT(*) FROM leads_bruts WHERE campaign_id = c.id AND statut IN ('audite','email_genere','envoye')) as nb_audites,
                    (SELECT COUNT(*) FROM emails_envoyes ee JOIN leads_bruts lb ON ee.lead_id = lb.id WHERE lb.campaign_id = c.id) as emails_envoyes,
                    (SELECT COUNT(*) FROM emails_envoyes ee JOIN leads_bruts lb ON ee.lead_id = lb.id WHERE lb.campaign_id = c.id AND ee.ouvert=1) as nb_ouverts,
                    (SELECT COUNT(*) FROM emails_envoyes ee JOIN leads_bruts lb ON ee.lead_id = lb.id WHERE lb.campaign_id = c.id AND ee.clique=1) as nb_cliques,
                    (SELECT COUNT(*) FROM emails_envoyes ee JOIN leads_bruts lb ON ee.lead_id = lb.id WHERE lb.campaign_id = c.id AND ee.repondu=1) as nb_reponses,
                    (SELECT COUNT(*) FROM emails_envoyes ee JOIN leads_bruts lb ON ee.lead_id = lb.id WHERE lb.campaign_id = c.id AND ee.rdv_confirme=1) as nb_rdv
                FROM campagnes c
                {where_clause}
                ORDER BY c.date_creation DESC
                LIMIT 100
            """, params).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_all_campaigns → {e}")
        return []


def get_campaign_by_id(camp_id: int) -> dict | None:
    try:
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM campagnes WHERE id = ?", (camp_id,)).fetchone()
            if not row:
                return None
            campaign = dict(row)
            stats = conn.execute("""
                SELECT
                    (SELECT COUNT(*) FROM leads_bruts WHERE campaign_id = ?) as leads_total,
                    (SELECT COUNT(*) FROM leads_bruts WHERE campaign_id = ? AND statut IN ('audite','email_genere','envoye')) as nb_audites,
                    (SELECT COUNT(*) FROM emails_envoyes ee JOIN leads_bruts lb ON ee.lead_id = lb.id WHERE lb.campaign_id = ?) as emails_envoyes
            """, (camp_id, camp_id, camp_id)).fetchone()
            campaign['leads_total'] = stats[0]
            campaign['nb_audites'] = stats[1]
            campaign['emails_envoyes'] = stats[2]
            return campaign
    except Exception as e:
        logger.error(f"get_campaign_by_id({camp_id}) → {e}")
        return None


def delete_campaign(camp_id: int):
    """Supprime une campagne."""
    try:
        with get_conn() as conn:
            conn.execute("DELETE FROM campagnes WHERE id = ?", (camp_id,))
            conn.commit()
    except Exception as e:
        logger.error(f"delete_campaign({camp_id}) → {e}")


def update_campaign(camp_id: int, **fields):
    """Met a jour des champs d'une campagne."""
    allowed = {"nom", "secteur", "ville", "nb_demande", "statut"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    try:
        with get_conn() as conn:
            sets = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [camp_id]
            conn.execute(f"UPDATE campagnes SET {sets} WHERE id = ?", values)
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"update_campaign({camp_id}) → {e}")
        return False
