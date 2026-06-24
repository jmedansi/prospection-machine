# -*- coding: utf-8 -*-
"""
scraper/sniper/pipeline.py — Orchestrateur du pipeline Sniper (Phases 1→4)

Flux :
  Phase 1 → ads_extractor   : keywords → [domaine, mot_cle, pays]
  Phase 2 → enricher         : domaine  → PageSpeed + Wappalyzer (en parallèle)
  Phase 3 → scoring          : données enrichies → tag_urgence + niveau (ou rejet)
  Phase 4 → database         : insert_lead() + insert_campaign()

Le pipeline est stateful : un dict _state est mis à jour en temps réel
pour que le dashboard puisse poller /api/sniper/status.

Usage programmatique :
    from scraper.sniper.pipeline import SniperPipeline
    p = SniperPipeline()
    p.run(keywords=["Boutique vêtement sport", "ERP PME"], country="fr")
"""

import concurrent.futures
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional

# Forcer l'encodage UTF-8 pour la sortie standard (Windows support)
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

logger = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ─── État partagé (pollable par le dashboard) ─────────────────────────────────

_state: Dict = {
    "running":       False,
    "phase":         None,   # "extraction" | "enrichissement" | "scoring" | "generation" | "done"
    "total":         0,      # annonceurs bruts extraits
    "processed":     0,      # enrichis jusqu'ici
    "accepted":      0,      # leads insérés en DB
    "rejected":      0,
    "errors":        0,
    "emails_generes": 0,     # emails générés automatiquement
    "logs":          [],     # derniers 50 messages
    "started_at":    None,
    "ended_at":      None,
    "current_kw":    "",     # keyword en cours d'extraction
    "pages_current": 0,      # pages parcourues pour le keyword courant
    "stop_requested": False,  # Flag pour arrêter proprement
}


def get_state() -> Dict:
    return dict(_state)


def reset_state() -> None:
    _state["running"] = False
    _state["phase"]   = None
    _state["stop_requested"] = False


def request_stop() -> None:
    """Demande l'arrêt du pipeline (à appeler depuis le dashboard)."""
    _state["stop_requested"] = True
    _log("🛑 Arrêt demandé par l'utilisateur", level="warning")


def is_stop_requested() -> bool:
    """Vérifie si un arrêt a été demandé."""
    return _state.get("stop_requested", False)


def _log(msg: str, level: str = "info", log_file: Optional[str] = None):
    """
    Loggue un message dans le logger, l'état (dashboard) et le fichier de campagne.
    Levels: info, success, warning, error, discovery
    """
    if level == "error":
        logger.error(msg)
    elif level == "warning":
        logger.warning(msg)
    else:
        logger.info(msg)

    prefix = {
        "info": "ℹ️",
        "success": "✅",
        "warning": "⚠️",
        "error": "🚨",
        "discovery": "🔍"
    }.get(level, "•")

    txt = f"[{datetime.now().strftime('%H:%M:%S')}] {prefix} {msg}"
    _state["logs"].append(txt)
    if len(_state["logs"]) > 500:
        _state["logs"].pop(0)
    
    if log_file:
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(txt + "\n")
        except Exception:
            pass


# ─── Phase 2 : Enrichissement d'un domaine ────────────────────────────────────

def _enrich_domain(domain_info: Dict) -> Optional[Dict]:
    """
    Enrichit un domaine avec PageSpeed (mobile + desktop) + Wappalyzer en parallèle.
    Retourne un dict complet ou None si inaccessible.
    """
    url = domain_info["domaine"]

    try:
        from auditeur.agents.web_analyzer import run_pagespeed, parse_html
        from scraper.sniper.wappalyzer_runner import analyze as wappalyzer_analyze

        pagespeed_mobile = {}
        pagespeed_desktop = {}
        wappalyzer_result = {}

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_ps_mobile = executor.submit(run_pagespeed, url, "mobile")
            future_ps_desktop = executor.submit(run_pagespeed, url, "desktop")
            future_wa = executor.submit(wappalyzer_analyze, url)

            try:
                pagespeed_mobile = future_ps_mobile.result(timeout=90)
            except Exception as e:
                logger.warning(f"PageSpeed mobile échoué pour {url}: {e}")
                pagespeed_mobile = {}

            try:
                pagespeed_desktop = future_ps_desktop.result(timeout=90)
            except Exception as e:
                logger.warning(f"PageSpeed desktop échoué pour {url}: {e}")
                pagespeed_desktop = {}

            try:
                wappalyzer_result = future_wa.result(timeout=45)
            except Exception as e:
                logger.warning(f"Wappalyzer échoué pour {url}: {e}")
                wappalyzer_result = {}

        # Fusion des résultats PageSpeed mobile + desktop
        pagespeed_result = {**pagespeed_mobile, **pagespeed_desktop}

        return {**domain_info, "pagespeed": pagespeed_result, "wappalyzer": wappalyzer_result}

    except Exception as e:
        logger.error(f"Enrichissement échoué pour {url}: {e}")
        return None
    finally:
        try:
            from core.browser import cleanup_sync_thread
            cleanup_sync_thread()
        except Exception:
            pass


# ─── Phase 3 + 4 : Scoring → DB ───────────────────────────────────────────────

def _store_lead(enriched: Dict, campaign_id: int, tag: str, niveau: int, reason: str, statut: str = "en_attente", log_file: Optional[str] = None, secteur: str = "") -> bool:
    """
    Applique le scoring et insère le lead qualifié en base.
    Retourne True si accepté, False si rejeté.
    """
    from scraper.sniper.scoring import build_donnees_audit

    url       = enriched["domaine"]
    mot_cle   = enriched.get("mot_cle", "")
    pays      = enriched.get("pays", "fr")
    pagespeed = enriched.get("pagespeed", {})
    wap       = enriched.get("wappalyzer", {})

    donnees = build_donnees_audit(pagespeed, wap, tag, niveau, reason, enriched)

    # Extraire un nom d'entreprise depuis le domaine (fallback)
    from urllib.parse import urlparse
    parsed = urlparse(url)
    netloc = parsed.netloc.lower().lstrip("www.")
    company_name = netloc.split(".")[0].replace("-", " ").title()

    # Données enrichies (Phase 1.5)
    email_valide = enriched.get("email_valide") or ""
    email_brut   = enriched.get("email_contact") or email_valide
    telephone    = enriched.get("telephone") or ""
    ceo_nom_complet = " ".join(filter(None, [
        enriched.get("ceo_prenom"), enriched.get("ceo_nom")
    ])) or company_name

    from database import insert_lead, update_lead, get_conn
    
    lead_data = {
        "campaign_id":    campaign_id,
        "nom":            ceo_nom_complet,
        "adresse":        "",
        "ville":          pays.upper(),
        "site_web":       url,
        "telephone":      telephone,
        "email":          email_brut,
        "email_valide":   email_valide,
        "mot_cle":        mot_cle,
        "category":       f"Annonceur — {mot_cle}",
        "source":         "ads",
        "tag_urgence":    tag,
        "niveau_urgence": niveau,
        "donnees_audit":  donnees,
        "statut":         statut,
        "secteur":        secteur,
    }

    # Si le lead a déjà un ID (sauvegarde hâtive), on UPDATE
    existing_id = enriched.get("id")
    if existing_id:
        update_lead(existing_id, lead_data)
        lead_id = existing_id
    else:
        lead_id = insert_lead(lead_data)

    if lead_id:
        _log(f"  ✓  {url} — {tag} niveau {niveau} | {reason}", log_file=log_file)

        # ── Cascade omnicanale : LinkedIn → Formulaire (si email introuvable) ──
        is_catch_all = enriched.get("is_catch_all", False)
        no_email     = not enriched.get("email_valide")
        ceo_prenom   = enriched.get("ceo_prenom")
        ceo_nom      = enriched.get("ceo_nom")

        if statut == "en_attente" and (is_catch_all or no_email) and ceo_prenom and ceo_nom and not _state.get("batch_mode"):
            _log(f"  ↩  {url} — email absent, bascule LinkedIn ({ceo_prenom} {ceo_nom})", log_file=log_file)
            try:
                import threading
                from sniper.linkedin_agent import send_linkedin_outreach

                with get_conn() as conn:
                    audit_row = conn.execute(
                        "SELECT id FROM leads_audites WHERE lead_id=? ORDER BY id DESC LIMIT 1",
                        (lead_id,)
                    ).fetchone()
                audit_id = audit_row[0] if audit_row else 0

                telephone = enriched.get("telephone") or ""

                def _omnichannel_wrapper():
                    # 1. LinkedIn
                    li_ok = send_linkedin_outreach(
                        audit_id=audit_id, lead_id=lead_id,
                        prenom=ceo_prenom, nom=ceo_nom,
                        company_name=company_name, domain=netloc, site_web=url,
                    )
                    if li_ok:
                        return

                    # 2. Formulaire de contact
                    form_ok = False
                    if url:
                        from sniper.form_sender import send_form_outreach
                        form_ok = send_form_outreach(
                            lead_id=lead_id, site_web=url,
                            prenom=ceo_prenom, nom=ceo_nom,
                        )
                    if form_ok:
                        return

                    # 3. WhatsApp (mobile FR uniquement)
                    if telephone:
                        from sniper.whatsapp_sender import send_whatsapp_outreach
                        send_whatsapp_outreach(
                            lead_id=lead_id, phone=telephone,
                            site_web=url, prenom=ceo_prenom, nom=ceo_nom,
                        )

                from services.task_worker import enqueue_task
                enqueue_task(_omnichannel_wrapper, label=f"Omnicanal ({ceo_prenom} {ceo_nom})")
            except Exception as e:
                logger.warning(f"Omnichannel outreach non lance pour {url}: {e}")

        return True

    return False


# ─── Pipeline principal ────────────────────────────────────────────────────────

class SniperPipeline:
    """
    Orchestrateur complet du pipeline Sniper.

    Usage :
        pipeline = SniperPipeline()
        pipeline.run(
            keywords=["Boutique vêtement sport Suisse", "Logiciel ERP PME"],
            country="fr",
            max_per_kw=8,
            parallel_enrich=3,
        )
    """

    def __init__(self):
        self.log_file = None
        self.secteur = ""

    def run(
        self,
        keywords:         List[str],
        country:          str = "fr",
        city:             str = "",
        max_per_kw:       int = 9999,
        pages_per_kw:     int = 100,
        parallel_enrich:  int = 3,
        campaign_name:    Optional[str] = None,
        batch_mode:       bool = False,
        min_leads:        int = 0,   # Quota minimum — déclenche la rotation de villes
        secteur:          str = "",  # Étiquette secteur
    ) -> Dict:
        """
        Exécute le pipeline complet.
        """
        if _state["running"]:
            return {"error": "Pipeline déjà en cours"}

        # Init état
        self.secteur = secteur
        _state.update({
            "running": True, "phase": "extraction",
            "total": 0, "processed": 0, "accepted": 0, "rejected": 0, "errors": 0,
            "emails_generes": 0, "current_kw": "", "pages_current": 0,
            "stop_requested": False,  # Réinitialisation cruciale
            "logs": [], "started_at": datetime.now().isoformat(), "ended_at": None,
            "batch_mode": batch_mode,
        })

        try:
            # ── Créer la campagne en DB ──────────────────────────────────────
            from database import insert_campaign
            if not campaign_name:
                campaign_name = f"Sniper_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # --- Initialisation du fichier de log persistant ---
            log_dir = os.path.join(ROOT, "data", "logs", "campaigns")
            os.makedirs(log_dir, exist_ok=True)
            safe_name = "".join([c if c.isalnum() or c in " _-" else "_" for c in campaign_name])
            self.log_file = os.path.join(log_dir, f"{safe_name}.log")
            
            with open(self.log_file, "w", encoding="utf-8") as f:
                f.write(f"=== CAMPAGNE : {campaign_name} ===\n")
                f.write(f"Début : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Pays : {country} | Ville : {city}\n")
                f.write(f"Mots-clés : {keywords}\n")
                f.write("-" * 50 + "\n\n")

            # Wrapper local pour capturer self.log_file
            def _log_local(msg, level="info"):
                _log(msg, level=level, log_file=self.log_file)

            campaign_id = insert_campaign(campaign_name, "ads", country, nb_demande=len(keywords) * max_per_kw)
            _log_local(f"Campagne créée : #{campaign_id} — {campaign_name}", "success")

            # ── Rotation de villes — état initial ────────────────────────────
            from core.city_rotator import CityRotator
            from database import get_conn
            from scraper.sniper.ads_extractor import extract_ads
            from sniper.enrichment.pre_filter import filter_batch
            from core.contact_finder import find_contacts
            from urllib.parse import urlparse as _urlparse

            rotator           = CityRotator(country=country, keywords=keywords, source="ads")
            original_keywords = list(keywords)
            if city:
                current_keywords = [f"{kw} {city}" if city.lower() not in kw.lower() else kw for kw in keywords]
                rotator._used.add(city)
                rotation_pass     = 0
            elif min_leads > 0:
                current_keywords = rotator.next_batch_multi(original_keywords, batch_size=4)
                rotator.mark_used(current_keywords)
                rotation_pass     = 1
            else:
                current_keywords = list(keywords)
                rotation_pass     = 0

            # ── Boucle Extraction → Enrichissement → Scoring (+ rotation villes) ─
            while True:
                if is_stop_requested():
                    _log_local("Arrêt demandé avant extraction")
                    break

                # — Phase 1 : Extraction —————————————————————————————
                _state["phase"] = "extraction"
                prefix = f"[Rotation #{rotation_pass}] " if rotation_pass else ""
                _log_local(f"Phase 1 {prefix}— Extraction ({len(current_keywords)} mots-clés, pays={country})", "info")

                with get_conn() as _c:
                    _rows = _c.execute(
                        "SELECT site_web FROM leads_bruts WHERE source='ads' "
                        "AND site_web IS NOT NULL AND site_web != ''"
                    ).fetchall()
                _known_domains = {
                    r["site_web"].lower().replace("://www.", "://").rstrip("/")
                    for r in _rows
                }
                _log_local(f"  {len(_known_domains)} domaines déjà en base (exclus)")

                # Callback pour le suivi temps réel + sauvegarde hâtive
                from database import insert_lead
                from urllib.parse import urlparse
                
                def _on_lead_discovered(lead):
                    url = lead.get("domaine", "")
                    # On évite les doublons déjà en base (double check au cas où l'extracteur en trouve)
                    norm_url = url.lower().replace("://www.", "://").rstrip("/")
                    if norm_url in _known_domains:
                        return
                    
                    _state["total"] += 1
                    _state["current_kw"] = lead.get("mot_cle", "")
                    
                    # Sauvegarde immédiate (Sécurité crash/coupure)
                    netloc = urlparse(url).netloc.lower().lstrip("www.")
                    company_name = netloc.split(".")[0].replace("-", " ").title()
                    
                    try:
                        lead["id"] = insert_lead({
                            "campaign_id": campaign_id,
                            "nom": company_name,
                            "site_web": url,
                            "mot_cle": lead.get("mot_cle", ""),
                            "ville": city or country.upper(),
                            "source": "ads",
                            "statut": "scraped",
                            "secteur": self.secteur,
                        })
                        _known_domains.add(norm_url) # Evite d'insérer 2 fois le même dans la même session
                        _log_local(f"Lead trouvé : {url} ({lead.get('mot_cle', '')})", "discovery")
                    except Exception as e:
                        logger.error(f"Erreur sauvegarde hâtive pour {url}: {e}")

                raw_leads = extract_ads(
                    current_keywords, country=country,
                    max_per_kw=max_per_kw, pages_per_kw=pages_per_kw,
                    on_lead_callback=_on_lead_discovered,
                    log_callback=_log_local
                )
                before = len(raw_leads)
                
                # Le filtrage des doublons est déjà géré par le callback + _known_domains.add
                # Mais on s'assure que raw_leads ne contient que les nouveaux
                raw_leads = [l for l in raw_leads if l.get("id") is not None]
                
                _log_local(f"  {len(raw_leads)} nouveaux annonceurs extraits et sauvegardés.")

                if raw_leads:
                    # — Phase 1.5 : Pré-filtre + contact/CEO —————————————
                    _log_local(f"Phase 1.5 — Pré-filtre + contacts ({len(raw_leads)} candidats)")

                    filtered_leads = filter_batch(raw_leads, top_n=9999, min_score=0)
                    _log_local(f"  {len(filtered_leads)}/{len(raw_leads)} leads retenus après pré-filtre")

                    # Parallélisation de la recherche de contacts (très lent sinon)
                    def _proc_contacts(lead):
                        url = lead.get("domaine", "")
                        _parsed = _urlparse(url)
                        domain = _parsed.netloc.lstrip("www.") or url
                        company_name = domain.split(".")[0].replace("-", " ").title()
                        try:
                            contacts = find_contacts(url, company_name, pays=lead.get("pays", "fr"))
                            lead.update(contacts)
                            _log_local(
                                f"  ✉  {url} — email={lead.get('email_valide','?')} "
                                f"CEO={lead.get('ceo_prenom','?')} {lead.get('ceo_nom','?')}"
                            )
                        except Exception as e:
                            logger.warning(f"contact_finder échoué pour {url}: {e}")
                        finally:
                            try:
                                from core.browser import cleanup_sync_thread
                                cleanup_sync_thread()
                            except Exception:
                                pass
                        return lead

                    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                        filtered_leads = list(executor.map(_proc_contacts, filtered_leads))

                    # — Phase 2 : Enrichissement (parallèle) ————————————
                    _state["phase"] = "enrichissement"
                    _log_local(f"Phase 2 — PageSpeed + Wappalyzer ({parallel_enrich} threads)")

                    with concurrent.futures.ThreadPoolExecutor(max_workers=parallel_enrich) as executor:
                        futures = {
                            executor.submit(_enrich_domain, lead): lead
                            for lead in filtered_leads
                        }
                        for future in concurrent.futures.as_completed(futures):
                            _state["processed"] += 1
                            enriched = future.result()
                            try:
                                from scraper.sniper.scoring import score_lead
                                if enriched is None:
                                    tag, niveau, reason = "rejete", 0, "Site inaccessible ou erreur enrichissement"
                                    statut = "rejete"
                                else:
                                    score = score_lead(enriched.get("pagespeed", {}), enriched.get("wappalyzer", {}), source="ads")
                                    if score is None:
                                        tag, niveau, reason = "rejete", 0, "Site performant ou pas d'urgence détectée"
                                        statut = "rejete"
                                    else:
                                        tag, niveau, reason = score
                                        statut = "en_attente"
                                        
                                    if enriched.get("_skip_reason"):
                                        tag, niveau, reason = "rejete", 0, enriched["_skip_reason"]
                                        statut = "rejete"

                                ok = _store_lead(enriched if enriched else futures[future], campaign_id, tag=tag, niveau=niveau, reason=reason, statut=statut, log_file=self.log_file, secteur=self.secteur)
                                if ok:
                                    if statut == "en_attente":
                                        _state["accepted"] += 1
                                    else:
                                        _state["rejected"] += 1
                            except Exception as e:
                                _state["errors"] += 1
                                logger.error(f"Enrichissement thread error: {e}")


                # — Vérification quota + rotation ————————————————————
                accepted_total = _state["accepted"]
                if min_leads > 0 and accepted_total < min_leads and rotator.has_more():
                    rotation_pass += 1
                    current_keywords = rotator.next_batch_multi(original_keywords, batch_size=4)
                    rotator.mark_used(current_keywords)
                    _log(
                        f"  [{accepted_total}/{min_leads} leads] Rotation #{rotation_pass} —"
                        f" {len(current_keywords)} nouvelles variantes"
                    )
                    continue
                break   # quota atteint ou rotation non demandée

            _log_local(
                f"Pipeline terminé — "
                f"{_state['accepted']} leads qualifiés, "
                f"{_state['rejected']} rejetés, "
                f"{_state['errors']} erreurs"
                + (f" [rotation x{rotation_pass}]" if rotation_pass else "")
            )

            # ── Phase 5 : Génération automatique des emails (hors boucle) ────
            if _state["accepted"] > 0:
                _state["phase"] = "generation"
                _log_local(f"Phase 5 — Génération emails ({_state['accepted']} leads)")
                try:
                    from sniper.email_generator import generate_sniper_emails_batch
                    result = generate_sniper_emails_batch(campaign_id=campaign_id, limit=500)
                    _state["emails_generes"] = result.get("success", 0)
                    _log_local(
                        f"  Emails générés : {_state['emails_generes']} "
                        f"(échecs: {result.get('errors', 0)}, "
                        f"ignorés: {result.get('skipped', 0)})"
                    )
                except Exception as e:
                    logger.error(f"Email generation erreur: {e}")
                    _log_local(f"  Génération emails échouée : {e}")

            return {
                "accepted":       _state["accepted"],
                "rejected":       _state["rejected"],
                "errors":         _state["errors"],
                "emails_generes": _state["emails_generes"],
                "campaign_id":    campaign_id,
            }

        except Exception as e:
            logger.error(f"Pipeline Sniper erreur critique: {e}")
            _log(f"ERREUR CRITIQUE : {e}", "error")
            return {"error": str(e)}

        finally:
            _state["running"]  = False
            _state["phase"]    = "done"
            _state["ended_at"] = datetime.now().isoformat()
