# -*- coding: utf-8 -*-
"""
database/repos/leads_repo.py — Repository leads_bruts

Couche d'accès aux données pour les leads.
Toutes les méthodes sont typées et documentées.
Pas de logique métier ici — uniquement des requêtes SQL.
"""
from __future__ import annotations
from database.connection import get_conn, logger


class LeadsRepo:
    """Accès CRUD à la table leads_bruts + jointure leads_audites."""

    # ─── LECTURE ────────────────────────────────────────────────────────────

    def get_by_id(self, lead_id: int, version: int = 4) -> dict | None:
        """
        Retourne un lead complet (leads_bruts + leads_audites + emails_envoyes en LEFT JOIN).
        """
        try:
            with get_conn() as conn:
                row = conn.execute("""
                    SELECT
                        lb.*,
                        la.mobile_score, la.desktop_score, la.score_urgence,
                        la.score_performance AS score_perf, la.score_seo,
                        la.lcp_ms AS lcp, la.email_objet, la.email_corps,
                        la.approuve, la.lien_rapport, la.lien_pdf,
                        la.probleme_principal, la.service_suggere,
                        la.cms_detected, la.template_used, la.template_variant,
                        la.ceo_prenom, la.ceo_nom, la.ceo_source,
                        la.email_valide AS email_valide_audit,
                        la.copywriting_mode, la.is_catch_all, la.mx_host,
                        la.statut_prospection, la.telephone_sniper,
                        la.screenshot_desktop, la.screenshot_mobile, la.rapport_html,
                        la.contact_mail, la.contact_wp, la.contact_li,
                        la.contact_fb, la.contact_appel, la.contact_autres,
                        ee.date_envoi AS sent_at, ee.ouvert AS is_opened,
                        ee.date_ouverture AS opened_at, ee.clique AS is_clicked,
                        ee.repondu AS is_replied, ee.statut_envoi AS email_status
                    FROM leads_bruts lb
                    LEFT JOIN leads_audites la ON la.lead_id = lb.id
                    LEFT JOIN (
                        SELECT * FROM emails_envoyes 
                        WHERE lead_id = ? 
                        ORDER BY date_envoi DESC LIMIT 1
                    ) ee ON ee.lead_id = lb.id
                    WHERE lb.id = ?
                    LIMIT 1
                """, (lead_id, lead_id)).fetchone()
                if not row: return None
                data = dict(row)
                # Récupérer les séquences d'email pour ce lead (relances planifiées / pending / sent)
                try:
                    seqs = conn.execute(
                        "SELECT id, email_type, statut, date_planifiee, date_envoi, email_objet, email_corps, telegram_msg_id FROM email_sequences WHERE lead_id=? ORDER BY date_planifiee ASC",
                        (lead_id,)
                    ).fetchall()
                    data['email_sequences'] = [dict(s) for s in seqs]
                except Exception:
                    data['email_sequences'] = []

                return self._normalize_v5(data) if version == 5 else self._normalize(data)
        except Exception as e:
            logger.error(f"LeadsRepo.get_by_id({lead_id}) → {e}")
            return None

    def get_all(self, statut: str = "tous", limit: int = 500,
                 page: int = 1, site: str = "tous",
                 email: str = "tous", sector: str = "tous",
                 search: str = "", campaign_id: int | None = None,
                 campaign_ids: list | None = None,
                 date_start: str | None = None, date_end: str | None = None,
                 source: str = "tous", tag: str = "", score: str = "tous",
                 notes: str = "tous", list_id: int | None = None) -> dict:
        """
        Liste paginée de leads avec jointure audit.
        """
        try:
            with get_conn() as conn:
                base = """
                    SELECT
                        lb.*,
                        la.id AS audit_id,
                        la.mobile_score, la.mobile_score AS score_mobile,
                        la.score_urgence,
                        la.score_performance AS score_perf,
                        la.score_seo,
                        la.email_objet, la.email_corps, la.approuve,
                        la.lien_rapport, la.lien_pdf,
                        la.probleme_principal, la.service_suggere,
                        la.statut_prospection,
                        COALESCE(NULLIF(la.email_valide, ''), NULLIF(lb.email_valide, '')) AS email_valide,
                        la.audit_partial,
                        la.ceo_prenom, la.ceo_nom, la.ceo_source,
                        la.screenshot_desktop, la.screenshot_mobile,
                        la.contact_mail, la.contact_wp, la.contact_li,
                        la.contact_fb, la.contact_appel, la.contact_autres
                    FROM leads_bruts lb
                    LEFT JOIN leads_audites la ON la.lead_id = lb.id
                """
                where, params = self._build_filters(statut, site, email, sector, search, campaign_id, campaign_ids, date_start, date_end, source=source, tag=tag, score=score, notes=notes, list_id=list_id)
                logger.info(f"LeadsRepo.get_all filters: where={where}, params={params}")
                count_row = conn.execute(
                    f"SELECT COUNT(*) FROM leads_bruts lb LEFT JOIN leads_audites la ON la.lead_id = lb.id {where}", params
                ).fetchone()
                total = count_row[0] if count_row else 0
                total_pages = max(1, (total + limit - 1) // limit)
                page = max(1, min(page, total_pages))
                offset = (page - 1) * limit
                rows = conn.execute(
                    f"{base} {where} ORDER BY lb.id DESC LIMIT ? OFFSET ?",
                    params + [limit, offset]
                ).fetchall()
                
                return {
                    "leads":       [self._normalize(dict(r)) for r in rows],
                    "total":       total,
                    "page":        page,
                    "total_pages": total_pages,
                }
        except Exception as e:
            logger.error(f"LeadsRepo.get_all → {e}")
            return {"leads": [], "total": 0, "page": 1, "total_pages": 1}

    def get_pending_audit(self, limit: int = 50) -> list[dict]:
        """Leads en attente d'audit (statut scrape ou en_attente, avec site web)."""
        try:
            with get_conn() as conn:
                rows = conn.execute("""
                    SELECT lb.*
                    FROM leads_bruts lb
                    LEFT JOIN leads_audites la ON la.lead_id = lb.id
                    WHERE lb.statut IN ('scraped', 'en_attente')
                      AND lb.site_web IS NOT NULL AND lb.site_web != ''
                      AND la.lead_id IS NULL
                    ORDER BY lb.id DESC
                    LIMIT ?
                """, (limit,)).fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"LeadsRepo.get_pending_audit → {e}")
            return []

    # ─── ÉCRITURE ───────────────────────────────────────────────────────────

    def update_statut(self, lead_id: int, statut: str) -> bool:
        """Met à jour le statut d'un lead. Retourne True si une ligne a été modifiée."""
        try:
            with get_conn() as conn:
                cur = conn.execute(
                    "UPDATE leads_bruts SET statut=? WHERE id=?", (statut, lead_id)
                )
                conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            logger.error(f"LeadsRepo.update_statut({lead_id}, {statut}) → {e}")
            return False

    def update_status_unified(self, lead_id: int, status: str) -> bool:
        """Met à jour le statut du lead de manière intelligente (brut ou prospection)."""
        try:
            with get_conn() as conn:
                row = conn.execute("SELECT source FROM leads_bruts WHERE id=?", (lead_id,)).fetchone()
                if not row: return False
                
                source = row['source']
                is_sniper = source in {"ads", "fb_ads", "transparency", "ecom", "tech", "jobs", "bodacc"}
                
                if is_sniper:
                    # On tente de mettre à jour l'audit d'abord
                    cur = conn.execute("UPDATE leads_audites SET statut_prospection=? WHERE lead_id=?", (status, lead_id))
                    if cur.rowcount == 0:
                        # Si pas d'audit, on met à jour le statut brut
                        conn.execute("UPDATE leads_bruts SET statut=? WHERE id=?", (status, lead_id))
                else:
                    conn.execute("UPDATE leads_bruts SET statut=? WHERE id=?", (status, lead_id))
                
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"LeadsRepo.update_status_unified({lead_id}) → {e}")
            return False

    def update_fields(self, lead_id: int, fields: dict) -> bool:
        """Met à jour des champs spécifiques d'un lead."""
        bruts_allowed = {"nom", "ville", "site_web", "adresse", "telephone", "email",
                         "mot_cle", "category", "statut", "email_valide",
                         "email_2", "telephone_2", "notes",
                         "nom_gerant", "prenom_gerant", "ml_extracted"}   # champs manuels (leads_bruts)
        audits_allowed = {"contact_mail", "contact_wp", "contact_li",
                          "contact_fb", "contact_appel", "contact_autres",
                          "email_valide", "ceo_prenom", "ceo_nom", "statut_prospection"}
        bruts_data  = {k: v for k, v in fields.items() if k in bruts_allowed}
        audits_data = {k: v for k, v in fields.items() if k in audits_allowed}
        if not bruts_data and not audits_data:
            return False
        try:
            with get_conn() as conn:
                # 1. Update leads_bruts
                if bruts_data:
                    sets = ", ".join(f"{k}=:{k}" for k in bruts_data)
                    conn.execute(f"UPDATE leads_bruts SET {sets} WHERE id=:id", {**bruts_data, "id": lead_id})
                
                # 2. Update leads_audites
                if audits_data:
                    audit = conn.execute("SELECT id FROM leads_audites WHERE lead_id=? ORDER BY id DESC LIMIT 1", (lead_id,)).fetchone()
                    if audit:
                        sets = ", ".join(f"{k}=:{k}" for k in audits_data)
                        conn.execute(f"UPDATE leads_audites SET {sets} WHERE id=:aid", {**audits_data, "aid": audit['id']})
                    else:
                        conn.execute("INSERT INTO leads_audites (lead_id) VALUES (?)", (lead_id,))
                        audit_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                        if audits_data:
                            sets = ", ".join(f"{k}=:{k}" for k in audits_data)
                            conn.execute(f"UPDATE leads_audites SET {sets} WHERE id=:aid", {**audits_data, "aid": audit_id})
                
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"LeadsRepo.update_fields({lead_id}) → {e}")
            return False

    def delete(self, lead_id: int) -> bool:
        """Supprime un lead et ses dépendances."""
        try:
            with get_conn() as conn:
                conn.execute("DELETE FROM leads_bruts WHERE id=?", (lead_id,))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"LeadsRepo.delete({lead_id}) → {e}")
            return False

    # ─── HELPERS PRIVÉS ─────────────────────────────────────────────────────

    def _build_filters(self, statut: str, site: str, email: str, sector: str, search: str = "",
                       campaign_id: int | None = None, campaign_ids: list | None = None,
                       date_start: str | None = None, date_end: str | None = None,
                       source: str = "tous", tag: str = "", score: str = "tous",
                       notes: str = "tous", list_id: int | None = None):
        clauses, params = [], []
        
        # Source Filter (Unified Maps/Sniper logic)
        if source == "maps":
            clauses.append("lb.source = 'maps'")
        elif source == "sniper":
            clauses.append("lb.source IN ('ads','fb_ads','transparency','ecom','tech','jobs','bodacc')")
        elif source and source != "tous":
            clauses.append("lb.source = ?")
            params.append(source)

        if tag:
            clauses.append("lb.tag_urgence = ?")
            params.append(tag)
            
        if notes == "sans":
            clauses.append("(lb.notes IS NULL OR lb.notes = '')")
        elif notes == "responsables":
            clauses.append("json_array_length(lb.ml_extracted, '$.persons') > 0")
        elif notes == "infos":
            clauses.append("("
                "lb.notes IS NOT NULL AND lb.notes != ''"
                " AND (json_array_length(lb.ml_extracted, '$.persons') = 0"
                "      OR json_array_length(lb.ml_extracted, '$.persons') IS NULL)"
                " AND ("
                "     (json_extract(lb.ml_extracted, '$.siret') IS NOT NULL"
                "      AND json_extract(lb.ml_extracted, '$.siret') != '')"
                "     OR"
                "     (json_extract(lb.ml_extracted, '$.adresse') IS NOT NULL"
                "      AND json_extract(lb.ml_extracted, '$.adresse') != '')"
                ")"
            ")")
        elif notes == "partiel":
            clauses.append("("
                "lb.notes IS NOT NULL AND lb.notes != ''"
                " AND (lb.ml_extracted IS NULL"
                "      OR lb.ml_extracted = ''"
                "      OR lb.ml_extracted = '{}'"
                "      OR ("
                "          (json_array_length(lb.ml_extracted, '$.persons') = 0"
                "           OR json_array_length(lb.ml_extracted, '$.persons') IS NULL)"
                "          AND (json_extract(lb.ml_extracted, '$.siret') IS NULL"
                "               OR json_extract(lb.ml_extracted, '$.siret') = '')"
                "          AND (json_extract(lb.ml_extracted, '$.adresse') IS NULL"
                "               OR json_extract(lb.ml_extracted, '$.adresse') = '')"
                "      )"
                ")"
            ")")

        if score == "bad":
            clauses.append("la.mobile_score > 0 AND la.mobile_score < 70")
        elif score == "good":
            clauses.append("la.mobile_score >= 70")
        elif score == "unscored":
            clauses.append("(la.mobile_score IS NULL OR la.mobile_score = 0)")

        if statut != "tous":
            # Mapping des statuts selon le cycle de vie du prospect (STRICT)
            # Un audit est valide s'il n'a pas d'erreur, et soit il a un score de perf, soit c'est une maquette/réputation/sans_site, soit le statut brut est 'audite'
            is_audit_valid = "(la.id IS NOT NULL AND la.audit_error IS NULL AND (la.score_performance > 0 OR la.template_used IN ('maquette', 'reputation', 'sans_site') OR lb.statut IN ('audite', 'email_genere', 'envoye', 'repondu')))"
            is_email_valid = f"({is_audit_valid} AND la.email_objet IS NOT NULL AND la.email_objet != '' AND la.email_corps IS NOT NULL AND la.email_corps != '')"
            
            statut_mapping = {
                # 1. À traiter (Nouveau ou Audit échoué)
                'en_attente':       f"lb.statut NOT IN ('archive', 'desabonne') AND (la.id IS NULL OR la.audit_error IS NOT NULL OR (la.score_performance = 0 AND la.template_used NOT IN ('maquette', 'reputation') AND lb.statut NOT IN ('audite', 'email_genere', 'envoye', 'repondu')))",
                
                # 2. Audité (Succès)
                'audite':           is_audit_valid,
                'non_audite':       f"lb.statut NOT IN ('archive', 'desabonne') AND (la.id IS NULL OR la.audit_error IS NOT NULL OR (la.score_performance = 0 AND la.template_used NOT IN ('maquette', 'reputation') AND lb.statut NOT IN ('audite', 'email_genere', 'envoye', 'repondu')))",
                
                # 3. E-mail prêt (Basé sur un audit valide)
                'email_pret':       is_email_valid,
                'email_non_genere': f"{is_audit_valid} AND (la.email_objet IS NULL OR la.email_objet = '')",
                
                # 4. Envoyé
                'envoye':           "(la.statut_prospection IN ('envoye', 'step1_envoye', 'email_sent') OR lb.statut IN ('envoye', 'email_sent'))",
                'non_envoye':       f"{is_email_valid} AND (la.statut_prospection NOT IN ('envoye', 'step1_envoye', 'email_sent') AND lb.statut NOT IN ('envoye', 'email_sent'))",
                
                # 5. Répondu
                'repondu':          "(la.statut_prospection = 'repondu' OR lb.statut = 'repondu')",
                'non_repondu':      "(la.statut_prospection IN ('envoye', 'step1_envoye', 'email_sent') OR lb.statut IN ('envoye', 'email_sent')) AND (la.statut_prospection != 'repondu' AND lb.statut != 'repondu')",
            }
            
            if statut in statut_mapping:
                clauses.append(statut_mapping[statut])
            else:
                # Statuts directs (scraped, en_attente, etc. dans leads_bruts)
                clauses.append("lb.statut = ?")
                params.append(statut)
        if site == "avec":
            clauses.append("(COALESCE(TRIM(lb.site_web), '') != '')")
        elif site == "sans":
            clauses.append("(COALESCE(TRIM(lb.site_web), '') = '')")

        if email == "avec":
            clauses.append("(COALESCE(TRIM(lb.email), '') != '' OR COALESCE(TRIM(lb.email_valide), '') != '' OR COALESCE(TRIM(la.email_valide), '') != '')")
        elif email == "sans":
            clauses.append("(COALESCE(TRIM(lb.email), '') = '' AND COALESCE(TRIM(lb.email_valide), '') = '' AND COALESCE(TRIM(la.email_valide), '') = '')")
        if sector != "tous":
            clauses.append("LOWER(COALESCE(lb.secteur,'')) = LOWER(?)")
            params.append(sector)
        if search:
            clauses.append("(LOWER(lb.nom) LIKE LOWER(?) OR LOWER(lb.site_web) LIKE LOWER(?))")
            params.extend([f"%{search}%", f"%{search}%"])
        if campaign_id:
            clauses.append("lb.campaign_id = ?")
            params.append(campaign_id)
        elif campaign_ids:
            placeholders = ",".join("?" * len(campaign_ids))
            clauses.append(f"lb.campaign_id IN ({placeholders})")
            params.extend(campaign_ids)
        if date_start:
            clauses.append("DATE(lb.date_scraping) >= ?")
            params.append(date_start)
        if date_end:
            clauses.append("DATE(lb.date_scraping) <= ?")
            params.append(date_end)
        if list_id:
            clauses.append("lb.id IN (SELECT lead_id FROM lead_list_items WHERE list_id = ?)")
            params.append(list_id)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        return where, params

    def _normalize(self, d: dict) -> dict:
        """[UNIFIED] Uniformise les noms de champs pour le frontend (ex-v4/v5)."""
        return {
            "id":                d.get("id"),
            "nom":               d.get("nom"),
            "ville":             d.get("ville"),
            "secteur":           d.get("secteur") or d.get("category"),
            "category":          d.get("category"),
            "source":            d.get("source") or "maps",
            "note":              d.get("rating"),
            "rating":            d.get("rating"),
            "avis":              d.get("nb_avis"),
            "nb_avis":           d.get("nb_avis"),
            "mot_cle":           d.get("mot_cle"),
            "tag_urgence":       d.get("tag_urgence"),
            "site_web":          d.get("site_web"),
            "email":             d.get("email"),
            "email_2":           d.get("email_2"),
            "telephone":         d.get("telephone"),
            "telephone_2":       d.get("telephone_2"),
            "adresse":           d.get("adresse"),
            "statut":            d.get("statut"),
            "statut_prospection": d.get("statut_prospection"),
            "score_urgence":     d.get("score_urgence"),
            "score_perf":        d.get("score_perf"),
            "score_seo":         d.get("score_seo"),
            "lcp":               d.get("lcp"),
            "email_objet":       d.get("email_objet"),
            "email_corps":       d.get("email_corps"),
            "approuve":          bool(d.get("approuve")),
            # Séquences de relance (list of {id,email_type,statut,date_planifiee,email_objet,email_corps})
            "email_sequences":   d.get("email_sequences") or [],
            "lien_rapport":      d.get("lien_rapport"),
            "lien_pdf":          d.get("lien_pdf"),
            "lien_maps":         d.get("lien_maps"),
            "probleme_principal": d.get("probleme_principal"),
            "service_suggere":   d.get("service_suggere"),
            "cms_detected":      d.get("cms_detected"),
            "template_used":     d.get("template_used"),
            "a_site":            bool(d.get("site_web")),
            "a_email":           bool(d.get("email")),
            "notes":             d.get("notes"),
            "email_valide":      d.get("email_valide") or d.get("email_valide_audit"),
            "email_valide_audit": d.get("email_valide_audit") or d.get("email_valide"),
            "ceo_prenom":        d.get("ceo_prenom"),
            "ceo_nom":           d.get("ceo_nom"),
            "ceo_source":        d.get("ceo_source"),
            "mobile_score":      int(d.get("mobile_score") or d.get("score_mobile") or 0),
            "score_mobile":      int(d.get("score_mobile") or d.get("mobile_score") or 0),
            "donnees_audit":     d.get("donnees_audit"),
            "date_scraping":     d.get("date_scraping"),
            # Champs d'envoi d'email
            "sent_at":           d.get("sent_at"),
            "is_opened":         bool(d.get("is_opened")),
            "opened_at":         d.get("opened_at"),
            "is_clicked":        bool(d.get("is_clicked")),
            "is_replied":        bool(d.get("is_replied")),
            "email_status":      d.get("email_status"),
            # Tracking
            "telephone_sniper":  d.get("telephone_sniper"),
            "copywriting_mode":  d.get("copywriting_mode"),
            "is_catch_all":      bool(d.get("is_catch_all")),
            "statut_display":    self._get_statut_display(d),
            "audit_id":          d.get("audit_id"),
            "audit_partial":     bool(d.get("audit_partial")),
            "kanban_status":     self._get_kanban_status(d),
            # Screenshots & mockup
            "screenshot_desktop": d.get("screenshot_desktop"),
            "screenshot_mobile":  d.get("screenshot_mobile"),
            "rapport_html":       d.get("rapport_html"),
            # Contact tracking
            "contact_mail":   int(d.get("contact_mail") or 0),
            "contact_wp":     int(d.get("contact_wp") or 0),
            "contact_li":     int(d.get("contact_li") or 0),
            "contact_fb":     int(d.get("contact_fb") or 0),
            "contact_appel":  int(d.get("contact_appel") or 0),
            "contact_autres": int(d.get("contact_autres") or 0),
        }

    def _normalize_v5(self, d: dict) -> dict:
        """Alias pour la compatibilité v5."""
        return self._normalize(d)

    def _get_kanban_status(self, d: dict) -> str:
        """Détermine la colonne Kanban selon le cycle de vie (avec vérification d'intégrité)."""
        sp = d.get("statut_prospection")
        sb = d.get("statut")
        
        # 0. Exclure les leads archivés et désabonnés
        if sb in ('archive', 'desabonne') or sp in ('archive', 'desabonne'):
            return "archive"
        
        # 1. Priorité aux réponses
        if sp == "repondu" or sb == "repondu":
            return "repondu"
        
        # 2. Contacté (canal de contact coché)
        if sp == "contacte":
            return "contacte"
        
        # 3. Déjà contacté
        sent_statuts = {"envoye", "step1_envoye", "email_sent", "lien_envoye", "linkedin_envoye", "formulaire_envoye", "whatsapp_envoye"}
        if sp in sent_statuts or sb in sent_statuts:
            return "envoye"
            
        # 4. Intégrité de l'audit
        score_valide = (d.get("score_mobile") or 0) > 0
        template_special = d.get("template_used") in ("maquette", "reputation")
        statut_force = sb in ("audite", "email_genere", "envoye", "repondu")
        
        has_valid_audit = d.get("audit_id") and not d.get("audit_error") and (score_valide or template_special or statut_force)
            
        # 5. Email prêt (Seulement si l'audit est valide et l'email complet)
        has_email = (d.get("email_objet") and d.get("email_objet").strip()) and (d.get("email_corps") and d.get("email_corps").strip())
        if has_valid_audit and has_email:
            return "email_genere"
            
        # 6. Audité (Succès uniquement)
        if has_valid_audit:
            return "audite"
            
        # 7. Par défaut : À traiter (Inclut les audits échoués)
        return "en_attente"

    def _get_statut_display(self, d: dict) -> dict:
        """Retourne le label et la couleur pour l'affichage unifié."""
        s = self._get_kanban_status(d)
        
        mapping = {
            "en_attente":   {"label": "À traiter",    "color": "#64748b"},
            "contacte":     {"label": "Contacté",     "color": "#92400e"},
            "audite":       {"label": "Audité",       "color": "#8b5cf6"},
            "email_genere": {"label": "Email prêt",    "color": "#10b981"},
            "envoye":       {"label": "Envoyé",       "color": "#3b82f6"},
            "repondu":      {"label": "Répondu ✓",    "color": "#f59e0b"},
        }
        
        # Gestion des cas spécifiques (bounced, positif, etc.)
        sp = d.get("statut_prospection")
        if sp == "positif":
            return {"label": "Positif", "color": "#10b981"}
        if sp == "bounced":
            return {"label": "Bounced", "color": "#ef4444"}
            
        # Cas d'erreur d'audit (si on n'a ni score mobile valide, ni un template spécial, ni un statut forcé)
        score_valide = (d.get("score_mobile") or 0) > 0
        template_special = d.get("template_used") in ("maquette", "reputation")
        statut_force = d.get("statut") in ("audite", "email_genere", "envoye", "repondu")
        
        if d.get("audit_id") and d.get("audit_error"):
            return {"label": "Audit Échoué", "color": "#ef4444"}
        elif d.get("audit_id") and not score_valide and not template_special and not statut_force:
            return {"label": "Audit Échoué", "color": "#ef4444"}
            
        return mapping.get(s, {"label": s.replace('_', ' ').capitalize(), "color": "#64748b"})


# Singleton partagé
leads_repo = LeadsRepo()
