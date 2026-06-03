# -*- coding: utf-8 -*-
from .connection import get_conn, logger, _serialize_json


def insert_audit(audit: dict) -> int | None:
    """Insère un audit complet. Retourne l'id."""
    try:
        logger.info(f"insert_audit START for lead_id={audit.get('lead_id')}")
        try:
            keys = list(audit.keys())
        except Exception:
            keys = []
        logger.debug(f"insert_audit keys: {keys}")
        audit = _serialize_json(audit, ['top3_problems', 'arguments'])
        audit_params = _build_audit_params(audit)
        with get_conn() as conn:
            existing = conn.execute(
                "SELECT id FROM leads_audites WHERE lead_id=?",
                (audit.get('lead_id'),)
            ).fetchone()
            if existing and existing['id'] is not None:
                # ── UPDATE ────────────────────────────────────────────────────
                audit_params['id'] = existing['id']
                logger.info(f"insert_audit -> UPDATE audit id={existing['id']}")
                try:
                    keys_check = ('mobile_score','desktop_score','score_performance','score_seo','score_urgence','lien_rapport','template_used')
                    small = {k: (audit_params[k] if k in keys_check else '...') for k in audit_params}
                    print(f"[DB-DEBUG] update params preview: {small}")
                except Exception:
                    pass
                conn.execute("""
                    UPDATE leads_audites SET
                        mobile_score=:mobile_score, desktop_score=:desktop_score, tablet_score=:tablet_score,
                        lcp_ms=:lcp_ms, fcp_ms=:fcp_ms, cls=:cls, render_blocking_scripts=:render_blocking_scripts,
                        uses_cache=:uses_cache, page_size_kb=:page_size_kb, has_https=:has_https,
                        has_meta_description=:has_meta_description, title_length=:title_length, h1_count=:h1_count,
                        has_schema=:has_schema, has_contact_button=:has_contact_button, tel_link=:tel_link,
                        images_without_alt=:images_without_alt, has_analytics=:has_analytics,
                        has_robots=:has_robots, has_sitemap=:has_sitemap, has_responsive_meta=:has_responsive_meta,
                        cms_detected=:cms_detected, visible_text_words=:visible_text_words,
                        score_performance=:score_performance, score_seo=:score_seo, score_gmb=:score_gmb, score_urgence=:score_urgence,
                        top3_problems=:top3_problems, service_suggere=:service_suggere, probleme_principal=:probleme_principal,
                        arguments=:arguments, rapport_resume=:rapport_resume, email_objet=:email_objet, email_corps=:email_corps,
                        approuve=:approuve, lien_rapport=:lien_rapport, lien_pdf=:lien_pdf, template_used=:template_used, nb_avis=:nb_avis,
                        audit_error=:audit_error, audit_partial=:audit_partial,
                        date_audit=datetime('now'), sheets_synced=0
                    WHERE id=:id
                """, audit_params)
                conn.commit()
                logger.info(f"insert_audit UPDATE committed for id={existing['id']}")
                return existing['id']
            else:
                # ── INSERT ────────────────────────────────────────────────────
                logger.info(f"insert_audit -> INSERT for lead_id={audit.get('lead_id')}")
                try:
                    keys_check = ('mobile_score','desktop_score','score_performance','score_seo','score_urgence','lien_rapport','template_used')
                    small = {k: (audit.get(k) if k in keys_check else '...') for k in audit}
                    print(f"[DB-DEBUG] insert params preview: {small}")
                except Exception:
                    pass
                conn.execute("""
                    INSERT INTO leads_audites
                    (lead_id, mobile_score, desktop_score, tablet_score,
                     lcp_ms, fcp_ms, cls, render_blocking_scripts,
                     uses_cache, page_size_kb, has_https,
                     has_meta_description, title_length, h1_count,
                     has_schema, has_contact_button, tel_link,
                     images_without_alt, has_analytics,
                     has_robots, has_sitemap, has_responsive_meta,
                     cms_detected, visible_text_words,
                     score_performance, score_seo, score_gmb, score_urgence,
                     top3_problems, service_suggere, probleme_principal,
                     arguments, rapport_resume, email_objet, email_corps,
                     approuve, lien_rapport, lien_pdf, template_used, nb_avis,
                     date_audit, sheets_synced)
                    VALUES
                    (:lead_id, :mobile_score, :desktop_score, :tablet_score,
                     :lcp_ms, :fcp_ms, :cls, :render_blocking_scripts,
                     :uses_cache, :page_size_kb, :has_https,
                     :has_meta_description, :title_length, :h1_count,
                     :has_schema, :has_contact_button, :tel_link,
                     :images_without_alt, :has_analytics,
                     :has_robots, :has_sitemap, :has_responsive_meta,
                     :cms_detected, :visible_text_words,
                     :score_performance, :score_seo, :score_gmb, :score_urgence,
                     :top3_problems, :service_suggere, :probleme_principal,
                     :arguments, :rapport_resume, :email_objet, :email_corps,
                     :approuve, :lien_rapport, :lien_pdf, :template_used, :nb_avis,
                     datetime('now'), 0)
                """, audit_params)
                conn.commit()
                row = conn.execute(
                    "SELECT id FROM leads_audites WHERE lead_id=?",
                    (audit.get('lead_id'),)
                ).fetchone()
                new_id = row['id'] if row else None
                logger.info(f"insert_audit INSERT committed, new id={new_id}")
                return new_id
    except Exception as e:
        logger.error(f"insert_audit -> {e}")
        raise


def _build_audit_params(audit: dict) -> dict:
    """Construit le dict de paramètres pour un audit."""
    return {
        'lead_id':                  audit.get('lead_id'),
        'mobile_score':             audit.get('mobile_score', 0),
        'desktop_score':            audit.get('desktop_score', 0),
        'tablet_score':             audit.get('tablet_score', 0),
        'lcp_ms':                   audit.get('lcp_ms', audit.get('mobile_lcp_ms', 0)),
        'fcp_ms':                   audit.get('fcp_ms', 0),
        'cls':                      audit.get('cls', 0),
        'render_blocking_scripts':  audit.get('render_blocking_scripts', 0),
        'uses_cache':               int(bool(audit.get('uses_cache', False))),
        'page_size_kb':             audit.get('page_size_kb', 0),
        'has_https':                int(bool(audit.get('has_https', False))),
        'has_meta_description':     int(bool(audit.get('has_meta_description', False))),
        'title_length':             audit.get('title_length', 0),
        'h1_count':                 audit.get('h1_count', 0),
        'has_schema':               int(bool(audit.get('has_schema', False))),
        'has_contact_button':       int(bool(audit.get('has_contact_button', False))),
        'tel_link':                 int(bool(audit.get('tel_link', False))),
        'images_without_alt':       audit.get('images_without_alt', 0),
        'has_analytics':            int(bool(audit.get('has_analytics', False))),
        'has_robots':               int(bool(audit.get('has_robots', False))),
        'has_sitemap':              int(bool(audit.get('has_sitemap', False))),
        'has_responsive_meta':      int(bool(audit.get('has_responsive_meta', False))),
        'cms_detected':             audit.get('cms_detected'),
        'visible_text_words':       audit.get('visible_text_words', 0),
        'score_performance':        audit.get('score_performance', audit.get('mobile_score', 0)),
        'score_seo':                audit.get('score_seo', 0),
        'score_gmb':                audit.get('score_gmb', 0),
        'score_urgence':            audit.get('score_urgence', audit.get('score_priorite', 0)),
        'top3_problems':            audit.get('top3_problems'),
        'service_suggere':          audit.get('service_suggere', ''),
        'probleme_principal':       audit.get('probleme_principal', ''),
        'arguments':                audit.get('arguments'),
        'rapport_resume':           audit.get('rapport_resume', ''),
        'email_objet':              audit.get('email_objet', ''),
        'email_corps':              audit.get('email_corps', ''),
        'approuve':                 int(bool(audit.get('approuve', False))),
        'lien_rapport':             audit.get('lien_rapport', ''),
        'lien_pdf':                 audit.get('lien_pdf', audit.get('lien_rapport', '')),
        'template_used':            audit.get('template_used', ''),
        'nb_avis':                 audit.get('nb_avis', 0),
        'rapport_html':            audit.get('rapport_html', ''),
        'screenshot_desktop':      audit.get('screenshot_desktop', ''),
        'screenshot_mobile':       audit.get('screenshot_mobile', ''),
        'audit_error':              audit.get('audit_error'),
        'audit_partial':            int(bool(audit.get('audit_partial', False))),
    }


def get_audits_ready_for_email() -> list:
    """Leads audités avec email généré et approuvé, non encore envoyés."""
    try:
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT
                    lb.id as lead_id, lb.nom, lb.email,
                    lb.ville, lb.category, lb.site_web, lb.rating, lb.nb_avis,
                    la.id as audit_id,
                    la.mobile_score, la.score_performance, la.score_seo, la.score_urgence,
                    la.lcp_ms, la.email_objet, la.email_corps, la.approuve,
                    la.lien_rapport, la.lien_pdf, la.probleme_principal
                FROM leads_audites la
                JOIN leads_bruts lb ON lb.id = la.lead_id
                WHERE la.email_corps IS NOT NULL
                AND la.email_corps != ''
                AND lb.email IS NOT NULL
                AND lb.email != ''
                AND lb.statut != 'envoye'
                ORDER BY la.score_urgence DESC
            """).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_audits_ready_for_email → {e}")
        return []


def get_audits_with_reports(date_start: str | None = None, date_end: str | None = None) -> list:
    """Leads audités ayant un rapport PDF généré."""
    try:
        params = []
        date_filter = ""
        if date_start and date_end:
            date_filter = " AND DATE(la.date_audit) >= ? AND DATE(la.date_audit) <= ?"
            params.extend([date_start, date_end])
        with get_conn() as conn:
            rows = conn.execute(f"""
                SELECT
                    lb.id, lb.nom, lb.ville, lb.category,
                    la.score_urgence, la.lien_rapport,
                    la.lien_pdf, la.date_audit
                FROM leads_audites la
                JOIN leads_bruts lb ON lb.id = la.lead_id
                WHERE la.lien_rapport IS NOT NULL
                AND la.lien_rapport != ''
                {date_filter}
                ORDER BY la.score_urgence DESC
            """, params).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_audits_with_reports → {e}")
        return []


def update_audit_email(lead_id: int, email_objet: str, email_corps: str, approuve: bool = False):
    """Met à jour l'email généré pour un lead audité."""
    try:
        with get_conn() as conn:
            conn.execute("""
                UPDATE leads_audites
                SET email_objet=?, email_corps=?, approuve=?
                WHERE lead_id=?
            """, (email_objet, email_corps, int(approuve), lead_id))
    except Exception as e:
        logger.error(f"update_audit_email({lead_id}) → {e}")


def update_audit_approval(lead_nom: str, approuve: bool):
    """Approuve ou rejette un email depuis le dashboard."""
    try:
        with get_conn() as conn:
            conn.execute("""
                UPDATE leads_audites
                SET approuve=?
                WHERE lead_id = (
                    SELECT id FROM leads_bruts
                    WHERE LOWER(nom)=LOWER(?) LIMIT 1
                )
            """, (int(approuve), lead_nom))
    except Exception as e:
        logger.error(f"update_audit_approval({lead_nom}) → {e}")


def update_audit_email_content(lead_nom: str, email_objet: str, email_corps: str):
    """Met à jour le contenu de l'email."""
    try:
        with get_conn() as conn:
            conn.execute("""
                UPDATE leads_audites
                SET email_objet=?, email_corps=?
                WHERE lead_id = (
                    SELECT id FROM leads_bruts
                    WHERE LOWER(nom)=LOWER(?) LIMIT 1
                )
            """, (email_objet, email_corps, lead_nom))
    except Exception as e:
        logger.error(f"update_audit_email_content({lead_nom}) → {e}")


def update_audit_pdf(lead_id: int, pdf_path: str):
    """Met à jour le chemin du PDF local."""
    try:
        with get_conn() as conn:
            conn.execute(
                "UPDATE leads_audites SET lien_pdf = ? WHERE lead_id = ?",
                (pdf_path, lead_id)
            )
            # Marquer aussi le statut comme audité
            conn.execute(
                "UPDATE leads_bruts SET statut='audite' WHERE id=? AND statut NOT IN ('email_genere','envoye','repondu','archive')",
                (lead_id,)
            )
            logger.info(f"Audit PDF mis à jour pour lead {lead_id}: {pdf_path}")
    except Exception as e:
        logger.error(f"update_audit_pdf({lead_id}) → {e}")
