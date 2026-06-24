# -*- coding: utf-8 -*-
"""
sniper/email_generator.py — Génération et stockage des emails Sniper

Lire sniper/README.md avant toute modification.

Responsabilité :
  - Lire un lead Sniper depuis leads_bruts (source IN 'ads','tech','jobs')
  - Parser donnees_audit (JSON)
  - Appeler sniper/copywriter.py pour générer l'email
  - Écrire le résultat dans leads_audites (INSERT OR REPLACE)
  - Mettre à jour leads_bruts.statut → 'email_genere'

Ce module N'envoie PAS d'emails.
L'envoi est géré par agents/expediteur (partagé avec l'ancien pipeline).

Connexion à l'ancien système (quand validé) :
  Dans services/email_generator.py, ajouter :
    if lead.get('source') in ('ads', 'tech', 'jobs'):
        from sniper.email_generator import generate_sniper_email_for_lead
        return generate_sniper_email_for_lead(lead_id)
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Sources Sniper reconnues
SNIPER_SOURCES = {"ads", "fb_ads", "transparency", "tech", "ecom", "jobs", "bodacc"}


def _parse_donnees_audit(raw: Optional[str]) -> dict:
    """Parse le JSON donnees_audit. Retourne {} si invalide."""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning("donnees_audit non parsable")
        return {}


def _discover_website_for_bodacc(
    company_name: str,
    ceo_prenom: str = "",
    ceo_nom: str = "",
) -> Optional[str]:
    """
    Tente de trouver le site web d'une entreprise BODACC via DuckDuckGo.
    Retourne l'URL propre ou None si introuvable.
    """
    import requests
    from urllib.parse import urlparse, quote_plus

    # Blacklist domaines génériques à rejeter
    _BLACKLIST = {
        "linkedin.com", "facebook.com", "instagram.com", "twitter.com",
        "youtube.com", "google.com", "google.fr", "bing.com",
        "societe.com", "pappers.fr", "infogreffe.fr", "verif.com",
        "kompass.com", "manageo.fr", "bodacc.fr", "legifrance.gouv.fr",
        "sirene.fr", "annuaire-entreprises.data.gouv.fr",
    }

    # Construire la requête : "COMPANY NAME" site officiel
    if not company_name:
        return None

    # Requête : "COMPANY NAME" CEO site officiel (plus précis avec le nom du dirigeant)
    ceo_full = f"{ceo_prenom} {ceo_nom}".strip()
    if ceo_full:
        query = f'"{company_name}" {ceo_full} site officiel'
    else:
        query = f'"{company_name}" site officiel'

    try:
        resp = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_redirect": 1, "no_html": 1},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.debug(f"DuckDuckGo search échoué pour '{company_name}': {e}")
        return None

    # AbstractURL = meilleur résultat DuckDuckGo
    candidate = data.get("AbstractURL") or data.get("Redirect") or ""
    if not candidate:
        # Parcourir RelatedTopics
        for topic in (data.get("RelatedTopics") or []):
            if isinstance(topic, dict) and topic.get("FirstURL"):
                candidate = topic["FirstURL"]
                break

    if not candidate:
        return None

    try:
        parsed = urlparse(candidate)
        netloc = parsed.netloc.lower().lstrip("www.")
        if not netloc or any(netloc == b or netloc.endswith("." + b) for b in _BLACKLIST):
            return None
        return f"{parsed.scheme}://{parsed.netloc.lower()}"
    except Exception:
        return None


def generate_sniper_email_for_lead(lead_id: int) -> bool:
    """
    Génère et stocke l'email pour un lead Sniper.

    1. Lit leads_bruts WHERE id=lead_id AND source IN (ads, tech, jobs)
    2. Parse donnees_audit
    3. Génère via sniper/copywriter.py
    4. INSERT OR REPLACE dans leads_audites
    5. Met à jour leads_bruts.statut = 'email_genere'

    Returns:
        True si succès, False sinon
    """
    from database.connection import get_conn
    from sniper.copywriter import generate_email

    try:
        with get_conn() as conn:
            row = conn.execute("""
                SELECT id, nom, site_web, email, email_valide, ville, category,
                       source, tag_urgence, niveau_urgence, donnees_audit, statut,
                       telephone
                FROM leads_bruts
                WHERE id = ?
            """, (lead_id,)).fetchone()

        if not row:
            logger.warning(f"generate_sniper_email_for_lead: lead {lead_id} introuvable")
            return False

        lead = dict(row)

        if lead.get("source") not in SNIPER_SOURCES:
            logger.warning(
                f"Lead {lead_id} ignoré — source='{lead.get('source')}' "
                f"(attendu: {SNIPER_SOURCES})"
            )
            return False

        # ── Découverte site web pour leads BODACC sans site_web ───────────────
        if lead.get("source") == "bodacc" and not lead.get("site_web"):
            donnees_tmp = _parse_donnees_audit(lead.get("donnees_audit"))
            company_raw = lead.get("nom", "")
            # Extraire la raison sociale depuis "Prénom Nom — RAISON SOCIALE"
            company_name = company_raw.split("—")[-1].strip() if "—" in company_raw else company_raw
            ceo_prenom_tmp = donnees_tmp.get("ceo_prenom", "")
            ceo_nom_tmp    = donnees_tmp.get("ceo_nom", "")
            found_site = _discover_website_for_bodacc(company_name, ceo_prenom_tmp, ceo_nom_tmp)
            if found_site:
                lead["site_web"] = found_site
                with get_conn() as conn:
                    conn.execute("UPDATE leads_bruts SET site_web=? WHERE id=?", (found_site, lead_id))
                    conn.commit()
                logger.info(f"BODACC lead {lead_id} — site trouvé : {found_site}")
            else:
                logger.info(f"BODACC lead {lead_id} — site introuvable, lead ignoré")
                return False

        tag     = lead.get("tag_urgence") or "perf"
        niveau  = int(lead.get("niveau_urgence") or 0)
        donnees = _parse_donnees_audit(lead.get("donnees_audit"))

        from core.audit_data import parse_donnees_audit as _parse_audit
        d             = _parse_audit(donnees)
        
        # Par défaut, on prend les données du JSON
        score         = d["score_mobile"]
        desktop_score = d["score_desktop"]
        score_seo     = d["score_seo"]
        lcp_ms        = d["lcp_ms"]
        cms           = d["cms"]
        server        = d["server"]

        # ── OVERRIDE : Si l'auditeur Playwright est déjà passé, on prend SES vraies mesures ──
        with get_conn() as conn:
            audit_row = conn.execute("""
                SELECT mobile_score, desktop_score, lcp_ms, score_seo, cms_detected
                FROM leads_audites WHERE lead_id = ?
            """, (lead_id,)).fetchone()
            
        if audit_row and audit_row["mobile_score"] and audit_row["mobile_score"] > 0:
            score         = audit_row["mobile_score"]
            desktop_score = audit_row["desktop_score"] or desktop_score
            lcp_ms        = audit_row["lcp_ms"] or lcp_ms
            score_seo     = audit_row["score_seo"] or score_seo
            cms           = audit_row["cms_detected"] or cms

        # CEO data depuis donnees_audit (injecté par pipeline Phase 1.5)
        ceo_prenom = donnees.get("ceo_prenom")
        ceo_nom    = donnees.get("ceo_nom")
        ceo_source = donnees.get("ceo_source", "not_found")
        email_valide     = lead.get("email_valide") or lead.get("email") or ""
        copywriting_mode = donnees.get("copywriting_mode", "transfert")
        telephone_sniper = lead.get("telephone") or donnees.get("telephone") or ""
        mx_host          = donnees.get("mx_host")
        is_catch_all     = int(donnees.get("is_catch_all", False))

        # Nom de contact : CEO uniquement — jamais le nom de l'entreprise
        nom_contact = f"{ceo_prenom} {ceo_nom or ''}".strip() if ceo_prenom else ""

        # Lien rapport : slug basé sur le domaine (gardé en DB, PAS injecté dans step 1)
        import re
        site = lead.get("site_web") or ""
        slug = re.sub(r"^https?://", "", site).rstrip("/").replace("/", "-")
        slug = re.sub(r"[^a-zA-Z0-9\-]", "", slug)[:60]
        lien_rapport = f"https://audit.incidenx.com/{slug}/" if slug else "https://incidenx.com"

        # Nom entreprise brut (pour BODACC/JOBS qui ont besoin des deux)
        entreprise_nom = lead.get("nom", "")
        if "—" in entreprise_nom:
            entreprise_nom = entreprise_nom.split("—")[-1].strip()

        # ── Override immobilier : mail secteur au lieu du template sniper ──
        secteur_lead = (lead.get("category") or lead.get("secteur") or "").lower()
        if "immo" in secteur_lead:
            from envoi.sequence_emails import get_mail_1
            mail1 = get_mail_1(secteur_lead)
            email_objet = mail1.get("subject", "Vos leads du soir et du weekend")
            body_text = mail1.get("body", "")
            # Remplacer [Prénom] par le prenom du CEO
            prenom = ceo_prenom or ''
            body_text = body_text.replace('[Prénom]', prenom if prenom else '')
            email_corps = (
                '<html><head><title>{}</title></head>'
                '<body><pre style="font-family:inherit;white-space:pre-wrap">{}</pre></body></html>'
            ).format(email_objet, body_text)
        else:
            # Step 1 : pas de lien dans le corps (stratégie 2-steps — meilleure délivrabilité)
            email_objet, email_corps = generate_email(
                nom          = nom_contact,
                site         = site,
                tag          = tag,
                score        = score,
                lcp_ms       = lcp_ms,
                cms          = cms,
                server       = server,
                niveau       = niveau,
                lien_rapport = "",   # intentionnellement vide — envoyé en step 2 sur réponse
                source       = lead.get("source", "ads"),
                entreprise   = entreprise_nom,
            )

        # Score d'urgence normalisé sur 100 pour compatibilité avec l'ancien pipeline
        score_urgence = min(100, niveau * 20)

        with get_conn() as conn:
            # ── Insérer seulement si l'enregistrement n'existe pas encore ─────
            conn.execute("""
                INSERT OR IGNORE INTO leads_audites
                (lead_id,
                 mobile_score, desktop_score, lcp_ms, cms_detected,
                 score_performance, score_seo, score_urgence,
                 probleme_principal, rapport_resume,
                 email_objet, email_corps,
                 lien_rapport, approuve,
                 template_used, date_audit,
                 statut_prospection,
                 email_valide, email_source, copywriting_mode,
                 ceo_prenom, ceo_nom, ceo_source,
                 telephone_sniper, mx_host, is_catch_all)
                VALUES
                (?,
                 ?, ?, ?, ?,
                 ?, ?, ?,
                 ?, ?,
                 ?, ?,
                 ?, 0,
                 'sniper', datetime('now'),
                 'a_contacter',
                 ?, ?, ?,
                 ?, ?, ?,
                 ?, ?, ?)
            """, (
                lead_id,
                score, desktop_score, lcp_ms, cms,
                score, score_seo, score_urgence,
                tag, donnees.get("reason", tag),
                email_objet, email_corps,
                lien_rapport,
                email_valide, donnees.get("email_source", ""), copywriting_mode,
                ceo_prenom, ceo_nom, ceo_source,
                telephone_sniper, mx_host, is_catch_all,
            ))

            # ── Mettre à jour uniquement les colonnes email/sniper ─────────────
            # NE PAS écraser les scores si l'auditeur Playwright a déjà tourné
            # (mobile_score > 0 = audit réel disponible → on le préserve)
            conn.execute("""
                UPDATE leads_audites SET
                    email_objet          = ?,
                    email_corps          = ?,
                    lien_rapport         = CASE WHEN lien_rapport IS NULL OR lien_rapport = '' THEN ? ELSE lien_rapport END,
                    template_used        = CASE WHEN mobile_score > 0 THEN template_used ELSE 'sniper' END,
                    statut_prospection   = COALESCE(statut_prospection, 'a_contacter'),
                    email_valide         = ?,
                    email_source         = ?,
                    copywriting_mode     = ?,
                    ceo_prenom           = ?,
                    ceo_nom              = ?,
                    ceo_source           = ?,
                    telephone_sniper     = ?,
                    mx_host              = ?,
                    is_catch_all         = ?,
                    -- Scores : écraser seulement si pas encore audité par Playwright
                    mobile_score         = CASE WHEN mobile_score > 0 THEN mobile_score ELSE ? END,
                    desktop_score        = CASE WHEN desktop_score > 0 THEN desktop_score ELSE ? END,
                    score_performance    = CASE WHEN score_performance > 0 THEN score_performance ELSE ? END,
                    score_seo            = CASE WHEN score_seo > 0 THEN score_seo ELSE ? END,
                    score_urgence        = CASE WHEN mobile_score > 0 THEN score_urgence ELSE ? END,
                    lcp_ms               = CASE WHEN mobile_score > 0 THEN lcp_ms ELSE ? END,
                    cms_detected         = CASE WHEN mobile_score > 0 THEN cms_detected ELSE ? END
                WHERE lead_id = ?
            """, (
                email_objet, email_corps, lien_rapport,
                email_valide, donnees.get("email_source", ""), copywriting_mode,
                ceo_prenom, ceo_nom, ceo_source,
                telephone_sniper, mx_host, is_catch_all,
                # scores conditionnels (utilisés seulement si mobile_score = 0)
                score, desktop_score, score, score_seo, score_urgence, lcp_ms, cms,
                lead_id,
            ))

            conn.execute(
                "UPDATE leads_bruts SET statut='email_genere' WHERE id=? AND statut NOT IN ('envoye','repondu','archive')",
                (lead_id,)
            )
            conn.commit()

        logger.info(f"Email Sniper stocké — lead {lead_id} | tag={tag} | objet={email_objet[:60]}")

        # Génération et publication du rapport HTML (non bloquant)
        import threading
        def _publish():
            try:
                from sniper.rapport_generator import generate_and_publish
                generate_and_publish(lead_id)
            except Exception as e:
                logger.warning(f"rapport_generator non lancé pour lead {lead_id}: {e}")
        threading.Thread(target=_publish, daemon=True).start()

        return True

    except Exception as e:
        logger.error(f"generate_sniper_email_for_lead({lead_id}) → {e}")
        return False


def generate_sniper_emails_batch(
    campaign_id: Optional[int] = None,
    limit: int = 100,
) -> dict:
    """
    Génère les emails pour tous les leads Sniper sans email.

    Args:
        campaign_id: Filtrer par campagne (None = toutes les campagnes Sniper)
        limit:       Max de leads à traiter en une passe

    Returns:
        {"success": int, "failed": int, "skipped": int}
    """
    from database.connection import get_conn

    try:
        with get_conn() as conn:
            query = """
                SELECT lb.id
                FROM leads_bruts lb
                LEFT JOIN leads_audites la ON la.lead_id = lb.id
                WHERE lb.source IN ('ads', 'fb_ads', 'transparency', 'tech', 'ecom', 'jobs', 'bodacc')
                  AND (la.email_corps IS NULL OR la.email_corps = '')
                  AND lb.statut NOT IN ('envoye', 'repondu', 'archive')
                  AND lb.donnees_audit IS NOT NULL
            """
            params: list = []
            if campaign_id is not None:
                query += " AND lb.campaign_id = ?"
                params.append(campaign_id)
            query += f" LIMIT {int(limit)}"

            rows = conn.execute(query, params).fetchall()

    except Exception as e:
        logger.error(f"generate_sniper_emails_batch: lecture leads → {e}")
        return {"success": 0, "failed": 0, "skipped": 0}

    success, failed, skipped = 0, 0, 0

    for row in rows:
        lead_id = row[0]
        try:
            ok = generate_sniper_email_for_lead(lead_id)
            if ok:
                success += 1
            else:
                skipped += 1
        except Exception as e:
            logger.error(f"Batch email Sniper — lead {lead_id} → {e}")
            failed += 1

    logger.info(
        f"Batch Sniper terminé — "
        f"{success} générés, {skipped} ignorés, {failed} erreurs"
    )
    return {"success": success, "failed": failed, "skipped": skipped}

# Alias pour compatibilité avec les routes dashboard
generate_sniper_emails = generate_sniper_emails_batch
