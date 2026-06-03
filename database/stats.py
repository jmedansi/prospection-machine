# -*- coding: utf-8 -*-
from .connection import get_conn, logger


def get_dashboard_stats(campaign_id: int | None = None, date_start: str | None = None, date_end: str | None = None, campaign_ids: str | None = None) -> dict:
    """Toutes les métriques cockpit."""
    try:
        with get_conn() as conn:
            stats = {}
            where_lead = "WHERE 1=1"
            where_email = "WHERE 1=1"
            params = []
            
            if campaign_ids:
                ids = [int(x.strip()) for x in campaign_ids.split(',') if x.strip().isdigit()]
                if ids:
                    placeholders = ','.join('?' * len(ids))
                    where_lead += f" AND campaign_id IN ({placeholders})"
                    where_email = f"WHERE lb.campaign_id IN ({placeholders})"
                    params.extend(ids)
            elif campaign_id:
                where_lead += " AND campaign_id = ?"
                where_email = "WHERE lb.campaign_id = ?"
                params.append(campaign_id)
                
            if date_start and date_end:
                where_lead += " AND DATE(date_scraping) >= ? AND DATE(date_scraping) <= ?"
                if "JOIN" in where_email:
                    where_email += " AND DATE(ee.date_envoi) >= ? AND DATE(ee.date_envoi) <= ?"
                else:
                    where_email += " AND DATE(date_envoi) >= ? AND DATE(date_envoi) <= ?"
                params.extend([date_start, date_end])

            # -- Pipeline leads --
            sql_leads = f"""
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN statut='en_attente' THEN 1 ELSE 0 END) AS en_attente,
                    SUM(CASE WHEN statut IN ('audite','email_genere','envoye','scheduled') THEN 1 ELSE 0 END) AS audites,
                    SUM(CASE WHEN site_web IS NOT NULL AND site_web != '' THEN 1 ELSE 0 END) AS avec_site,
                    SUM(CASE WHEN email IS NOT NULL AND email != '' THEN 1 ELSE 0 END) AS avec_email
                FROM leads_bruts
                {where_lead}
            """
            r = conn.execute(sql_leads, params).fetchone()
            stats['leads_scrapes'] = r['total'] or 0
            stats['leads_attente']   = r['en_attente'] or 0
            stats['leads_site']      = r['avec_site'] or 0
            stats['emails_trouves']  = r['avec_email'] or 0

            # -- Leads audités --
            sql_audited = f"""
                SELECT COUNT(DISTINCT la.lead_id) AS total
                FROM leads_audites la
                JOIN leads_bruts lb ON la.lead_id = lb.id
                {where_lead.replace('campaign_id', 'lb.campaign_id')}
            """
            r_audited = conn.execute(sql_audited, params).fetchone()
            stats['leads_audites'] = r_audited['total'] or 0
            stats['leads_en_attente'] = max(0, (r['avec_site'] or 0) - stats['leads_audites'])
            stats['leads_sans_site'] = (r['total'] or 0) - (r['avec_site'] or 0)

            # -- Emails envoyés --
            sql_emails = f"""
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN ouvert=1 THEN 1 ELSE 0 END) AS ouverts,
                    SUM(CASE WHEN repondu=1 THEN 1 ELSE 0 END) AS repondus,
                    SUM(CASE WHEN clique=1 THEN 1 ELSE 0 END) AS cliques,
                    SUM(CASE WHEN type_reponse='positive' THEN 1 ELSE 0 END) AS positifs,
                    SUM(CASE WHEN rdv_confirme=1 THEN 1 ELSE 0 END) AS rdv
                FROM emails_envoyes ee
                JOIN leads_bruts lb ON ee.lead_id = lb.id
                {where_email}
                AND ee.bounce = 0 AND ee.spam = 0
            """
            r_emails = conn.execute(sql_emails, params).fetchone()
            envoyes = r_emails['total'] or 0
            stats['envoyes']             = envoyes
            stats['emails_ouverts']      = r_emails['ouverts'] or 0
            stats['emails_repondus']     = r_emails['repondus'] or 0
            stats['reponses_positives']  = r_emails['positifs'] or 0
            stats['rdv_obtenus']         = r_emails['rdv'] or 0

            # -- Bounces & Spam --
            r_bounce = conn.execute(f"""
                SELECT 
                    SUM(CASE WHEN bounce=1 OR statut_envoi='bounced' THEN 1 ELSE 0 END) AS bounces,
                    SUM(CASE WHEN spam=1 OR statut_envoi='spam' THEN 1 ELSE 0 END) AS spam
                FROM emails_envoyes ee
                JOIN leads_bruts lb ON ee.lead_id = lb.id
                {where_email}
            """, params).fetchone()
            stats['bounces'] = r_bounce['bounces'] or 0
            stats['spam'] = r_bounce['spam'] or 0
            stats['nb_envoyes'] = envoyes + stats['bounces'] + stats['spam']

            if envoyes > 0:
                stats['taux_ouverture'] = round((r_emails['ouverts'] or 0) / envoyes * 100)
                stats['taux_clic']      = round((r_emails['cliques'] or 0) / envoyes * 100)
                stats['taux_reponse']   = round((r_emails['repondus'] or 0) / envoyes * 100)
                stats['taux_rdv']       = round((r_emails['rdv'] or 0) / envoyes * 100)
                stats['indice_perf']    = round(
                    stats.get('taux_ouverture', 0) * 0.15 +
                    stats.get('taux_clic', 0)      * 0.15 +
                    stats.get('taux_reponse', 0)   * 0.35 +
                    stats.get('taux_rdv', 0)       * 0.35
                )
            else:
                stats['taux_ouverture'] = 0
                stats['taux_clic']      = 0
                stats['taux_reponse']   = 0
                stats['taux_rdv']       = 0
                stats['indice_perf']    = 0

            # -- Audits & Rapports --
            sql_audits = f"""
                SELECT
                    AVG(mobile_score) AS avg_mobile,
                    AVG(score_seo) AS avg_seo,
                    AVG(score_urgence) AS avg_score,
                    SUM(CASE WHEN score_urgence >= 7 THEN 1 ELSE 0 END) AS prioritaires,
                    SUM(CASE WHEN email_corps IS NOT NULL AND email_corps != '' THEN 1 ELSE 0 END) AS avec_email_genere,
                    SUM(CASE WHEN lien_rapport IS NOT NULL AND lien_rapport != '' THEN 1 ELSE 0 END) AS avec_rapport
                FROM leads_audites
                JOIN leads_bruts lb ON leads_audites.lead_id = lb.id
                {where_lead.replace('campaign_id', 'lb.campaign_id')}
            """
            r = conn.execute(sql_audits, params).fetchone()
            stats['score_moyen']         = round(r['avg_score'] or 0, 1)
            stats['mobile_moyen']        = round(r['avg_mobile'] or 0, 1)
            stats['seo_moyen']           = round(r['avg_seo'] or 0, 1)
            stats['leads_prioritaires']  = r['prioritaires'] or 0
            stats['emails_prets']        = r['avec_email_genere'] or 0
            stats['pdfs_generes']        = r['avec_rapport'] or 0

            # -- Quotas API --
            r_groq = conn.execute("SELECT COUNT(*) FROM leads_audites WHERE DATE(date_audit) = DATE('now')").fetchone()
            from config_manager import get_config
            cfg = get_config()
            stats['quotas'] = {
                'groq':   r_groq[0] if r_groq else 0,
                'resend': envoyes,
                'brevo':  cfg.get('brevo_usage', 0) or 0,
                'hunter': cfg.get('hunter_usage', 0) or 0,
                'carbone': cfg.get('carbone_usage', 0) or 0,
                'gemini': cfg.get('gemini_usage', 0) or 0,
                'anthropic': cfg.get('anthropic_usage', 0) or 0,
                'pagespeed': cfg.get('pagespeed_usage', 0) or 0
            }
            # -- ROI (Phase 4.4) --
            avg_basket = cfg.get('average_basket', 1500)
            stats['projected_roi'] = (stats['emails_repondus'] or 0) * avg_basket

            return stats
    except Exception as e:
        logger.error(f"get_dashboard_stats → {e}")
        return {}


def get_leads_for_dashboard(campaign_id: int | None = None, date_start: str | None = None, date_end: str | None = None, campaign_ids: str | None = None, limit: int = 500) -> list:
    """Retourne les leads enrichis pour le dashboard."""
    try:
        where_clause = "WHERE 1=1"
        params = []
        if campaign_ids:
            ids = [int(x.strip()) for x in campaign_ids.split(',') if x.strip().isdigit()]
            if ids:
                placeholders = ','.join('?' * len(ids))
                where_clause += f" AND lb.campaign_id IN ({placeholders})"
                params.extend(ids)
        elif campaign_id:
            where_clause += " AND lb.campaign_id = ?"
            params.append(campaign_id)
        if date_start and date_end:
            where_clause += " AND DATE(lb.date_scraping) >= ? AND DATE(lb.date_scraping) <= ?"
            params.extend([date_start, date_end])
            
        with get_conn() as conn:
            sql = f"""
                SELECT lb.*, la.score_performance AS score_perf, la.score_seo, la.score_urgence,
                       la.lcp_ms AS lcp, la.lien_rapport, la.email_corps, la.email_objet, la.approuve, la.probleme_principal
                FROM leads_bruts lb
                LEFT JOIN leads_audites la ON la.lead_id = lb.id
                {where_clause}
                ORDER BY lb.date_scraping DESC
                LIMIT {limit}
            """
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_leads_for_dashboard → {e}")
        return []


def get_niche_performance():
    """Retourne les performances par niche."""
    try:
        with get_conn() as conn:
            return conn.execute("""
                SELECT lb.category, lb.ville,
                       COUNT(ee.id) as envois, 
                       COALESCE(SUM(ee.clique), 0) as clics,
                       COALESCE(SUM(ee.repondu), 0) as reponses,
                       (CAST(COALESCE(SUM(ee.clique), 0) AS FLOAT) / NULLIF(COUNT(ee.id), 0)) * 100 as taux_clic
                FROM emails_envoyes ee
                JOIN leads_bruts lb ON ee.lead_id = lb.id
                GROUP BY lb.category, lb.ville
                HAVING envois > 5
                ORDER BY taux_clic DESC
                LIMIT 20
            """).fetchall()
    except Exception as e:
        logger.error(f"get_niche_performance -> {e}")
        return []


def get_ab_test_performance():
    """Performances A/B test."""
    try:
        with get_conn() as conn:
            return conn.execute("""
                SELECT 
                    la.template_used as profile,
                    ee.template_variant as variant,
                    COUNT(ee.id) as envois,
                    COALESCE(SUM(ee.ouvert), 0) as ouverts,
                    COALESCE(SUM(ee.clique), 0) as clics,
                    COALESCE(SUM(ee.repondu), 0) as reponses
                FROM emails_envoyes ee
                JOIN leads_audites la ON ee.lead_id = la.lead_id
                WHERE la.template_used IN ('A', 'B', 'C', 'D')
                GROUP BY la.template_used, ee.template_variant
                ORDER BY la.template_used, ee.template_variant
            """).fetchall()
    except Exception as e:
        logger.error(f"get_ab_test_performance -> {e}")
        return []
