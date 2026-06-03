# -*- coding: utf-8 -*-
"""
scraper/sniper/fb_ads_pipeline.py — Pipeline Meta Ad Library (Source FB ADS)

Flux :
  Phase 1   → fb_ads_browser_extractor : mots-clés → annonceurs Meta actifs
  Phase 1.5 → qualification sans site  : fan_count + ancienneté pub
  Phase 2/3 → enrichissement + scoring (parallèle, avec timeouts stricts)
  Phase 4   → insert leads_bruts (source='fb_ads')

État partagé pollable via get_state().
"""

import concurrent.futures
import json
import logging
import os
import sys
import traceback
from datetime import datetime, date
from typing import Dict, List, Optional
from urllib.parse import urlparse, quote, urlunparse
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ─── Constantes ───────────────────────────────────────────────────────────────

_MIN_FAN_COUNT   = 100   # au moins 100 abonnés
_MIN_AD_AGE_DAYS = 7     # pub active depuis au moins 7 jours

_VALID_LOG_LEVELS = {"debug", "info", "warning", "error", "critical"}


# ─── État partagé ─────────────────────────────────────────────────────────────

_STATE_DEFAULTS: Dict = {
    "running":        False,
    "phase":          None,
    "total":          0,
    "processed":      0,
    "accepted":       0,
    "rejected":       0,
    "no_site":        0,
    "errors":         0,
    "logs":           [],
    "started_at":     None,
    "ended_at":       None,
    "stop_requested": False,
}

_state: Dict = dict(_STATE_DEFAULTS)


def get_state() -> Dict:
    return dict(_state)


def reset_state() -> None:
    """Reset complet — inclut stop_requested et tous les compteurs."""
    _state.update(_STATE_DEFAULTS)
    _state["logs"] = []   # nouvelle liste, pas une ref partagée


def request_stop():
    """Demande l'arrêt du pipeline FB Ads."""
    _state["stop_requested"] = True
    _log("Arrêt demandé par l'utilisateur", "warning")


def is_stop_requested() -> bool:
    return _state.get("stop_requested", False)


def _log(msg: str, level: str = "info"):
    level = level if level in _VALID_LOG_LEVELS else "info"
    getattr(logger, level)(msg)
    _state["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    if len(_state["logs"]) > 100:
        _state["logs"].pop(0)


# ─── Critères éligibilité sans site ───────────────────────────────────────────

def _is_eligible_no_site(lead: Dict) -> bool:
    if lead.get("fan_count", 0) < _MIN_FAN_COUNT:
        return False
    start_str = lead.get("ad_start", "")
    if start_str:
        try:
            ad_date  = datetime.fromisoformat(start_str[:10]).date()
            age_days = (date.today() - ad_date).days
            if age_days < _MIN_AD_AGE_DAYS:
                return False
        except Exception:
            pass
    return True


# ─── Test de joignabilité ──────────────────────────────────────────────────────

def _is_site_reachable(url: str, timeout: int = 6) -> tuple[bool, str]:
    """HEAD request rapide — retourne (reachable, reason)."""
    try:
        p        = urlparse(url)
        safe_url = urlunparse(p._replace(path=quote(p.path)))
        req      = urllib.request.Request(
            safe_url, method="HEAD",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.getcode()
            if code in (403, 401, 407):
                return False, f"Accès refusé (HTTP {code})"
            return True, ""
    except urllib.error.HTTPError as e:
        if e.code in (403, 401, 407):
            return False, f"Accès refusé (HTTP {e.code})"
        return True, ""   # 404/500 → on tente quand même l'audit
    except Exception as e:
        return False, f"Site inaccessible : {type(e).__name__}"


# ─── Enrichissement d'un lead avec site ───────────────────────────────────────

def _enrich_with_site(lead: Dict) -> Optional[Dict]:
    """Contact + PageSpeed + Wappalyzer — timeouts stricts."""
    url          = lead.get("site_web", "")
    domain       = urlparse(url).netloc.lstrip("www.")
    company_name = lead.get("page_name", domain.split(".")[0].replace("-", " ").title())

    # Test de joignabilité rapide (6s max)
    reachable, reason = _is_site_reachable(url)
    if not reachable:
        logger.warning(f"[FB] Site inaccessible, audit ignoré : {url} — {reason}")
        lead["pagespeed"]    = {}
        lead["wappalyzer"]   = {}
        lead["_skip_reason"] = reason
        return lead

    # Contact finder
    try:
        from core.contact_finder import find_contacts
        lead.update(find_contacts(url, company_name))
    except Exception as e:
        logger.warning(f"[FB] contact_finder {url}: {type(e).__name__}: {e}")

    # PageSpeed + Wappalyzer en parallèle (25s + 15s)
    try:
        from auditeur.agents.web_analyzer import run_pagespeed
        from scraper.sniper.wappalyzer_runner import analyze as wap_analyze

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            f_ps = ex.submit(run_pagespeed, url, "mobile")
            f_wa = ex.submit(wap_analyze, url)
            try:
                lead["pagespeed"] = f_ps.result(timeout=25)
            except concurrent.futures.TimeoutError:
                logger.warning(f"[FB] PageSpeed timeout (25s) : {url}")
                lead["pagespeed"] = {}
            except Exception as e:
                logger.warning(f"[FB] PageSpeed erreur {url}: {type(e).__name__}")
                lead["pagespeed"] = {}
            try:
                lead["wappalyzer"] = f_wa.result(timeout=15)
            except concurrent.futures.TimeoutError:
                logger.warning(f"[FB] Wappalyzer timeout (15s) : {url}")
                lead["wappalyzer"] = {}
            except Exception as e:
                logger.warning(f"[FB] Wappalyzer erreur {url}: {type(e).__name__}")
                lead["wappalyzer"] = {}
    except Exception as e:
        logger.warning(f"[FB] pagespeed/wap init {url}: {e}")
        lead.setdefault("pagespeed",  {})
        lead.setdefault("wappalyzer", {})

    return lead


# ─── Insert lead en base ───────────────────────────────────────────────────────

def _store_lead(lead: Dict, campaign_id: int, tag: str, niveau: int, reason: str, statut: str = "en_attente") -> bool:
    from database import insert_lead

    url          = lead.get("site_web") or ""
    domain       = urlparse(url).netloc.lstrip("www.") if url else ""
    company_name = lead.get(
        "page_name",
        domain.split(".")[0].replace("-", " ").title() if domain else "Inconnu"
    )

    donnees = json.dumps({
        "score_mobile": lead.get("pagespeed", {}).get("mobile_score"),
        "cms":          lead.get("wappalyzer", {}).get("cms"),
        "cdn":          lead.get("wappalyzer", {}).get("cdn"),
        "fan_count":    lead.get("fan_count", 0),
        "page_id":      lead.get("page_id", ""),
        "ad_id":        lead.get("ad_id", ""),
        "ad_start":     lead.get("ad_start", ""),
        "ad_body":      lead.get("ad_body", ""),
        "tag":          tag,
        "niveau":       niveau,
        "reason":       reason,
        "skip_reason":  lead.get("_skip_reason"),
    }, ensure_ascii=False)

    lead_id = insert_lead({
        "campaign_id":    campaign_id,
        "nom":            company_name,
        "adresse":        "",
        "ville":          lead.get("pays", "FR"),
        "site_web":       url,
        "telephone":      lead.get("telephone", ""),
        "email":          lead.get("email_valide", ""),
        "email_valide":   lead.get("email_valide", ""),  # stocker l'email réel, pas "Valide"
        "mot_cle":        lead.get("mot_cle", ""),
        "category":       lead.get("category", "Annonceur Meta"),
        "source":         "fb_ads",
        "tag_urgence":    tag,
        "niveau_urgence": niveau,
        "donnees_audit":  donnees,
        "statut":         statut,
    })
    return bool(lead_id)


# ─── Pipeline principal ────────────────────────────────────────────────────────

class FbAdsPipeline:

    def run(
        self,
        search_terms:  List[str],
        country:       str = "FR",
        city:          str = "",
        max_pages:     int = 5,
        parallel:      int = 3,
        campaign_name: Optional[str] = None,
        min_leads:     int = 0,   # Quota minimum — déclenche la rotation de villes
    ) -> Dict:

        if _state["running"]:
            return {"error": "Pipeline FB Ads déjà en cours"}

        # Reset COMPLET — stop_requested inclus
        _state.update({
            **_STATE_DEFAULTS,
            "running":    True,
            "phase":      "init",
            "logs":       [],
            "started_at": datetime.now().isoformat(),
            "ended_at":   None,
            "stop_requested": False,
        })

        campaign_id = None
        try:
            from database import insert_campaign
            if not campaign_name:
                campaign_name = f"Sniper FB Ads — {country} — {datetime.now().strftime('%d/%m %H:%M')}"
            campaign_id = insert_campaign(
                campaign_name, "fb_ads", country,
                nb_demande=len(search_terms) * 50
            )
            _log(f"Campagne créée : #{campaign_id} — {campaign_name}")

            # ── Rotation de villes — état initial ──────────────────────────
            from core.city_rotator import CityRotator
            rotator           = CityRotator(country=country.lower()[:2], keywords=search_terms, source="fb_ads")
            original_terms    = list(search_terms)
            if city:
                current_terms = [f"{kw} {city}" if city.lower() not in kw.lower() else kw for kw in search_terms]
                rotator._used.add(city)
                rotation_pass     = 0
            else:
                current_terms = rotator.next_batch_multi(original_terms, batch_size=3)
                rotator.mark_used(current_terms)
                rotation_pass     = 1

            # ── Boucle Extraction → Qualification → Enrichissement (+ rotation villes) ─
            while True:
                if is_stop_requested():
                    _log("Arrêt demandé avant extraction", "warning")
                    break

                # — Phase 1 : Extraction ──────────────────────────────────────
                _state["phase"] = "extraction"
                prefix = f"[Rotation #{rotation_pass}] " if rotation_pass else ""
                _log(f"Phase 1 {prefix}— Meta Ad Library ({len(current_terms)} terme(s), pays={country})")

                from scraper.sniper.fb_ads_browser_extractor import extract_fb_ads
                try:
                    raw_leads = extract_fb_ads(current_terms, country=country, max_pages=max_pages)
                except Exception as e:
                    _log(f"ERREUR extraction navigateur : {type(e).__name__}: {e}", "error")
                    logger.error(f"[FB] Extraction échouée: {traceback.format_exc()}")
                    raw_leads = []

                _state["total"] += len(raw_leads)
                _log(f"  {len(raw_leads)} annonceur(s) extrait(s)")

                if raw_leads:
                    with_site    = [l for l in raw_leads if l.get("has_site")]
                    without_site = [l for l in raw_leads if not l.get("has_site")]
                    _log(f"  Avec site : {len(with_site)} | Sans site : {len(without_site)}")

                    if not is_stop_requested():
                        # — Phase 1.5 : Sans site → critères création ────────
                        _state["phase"] = "qualification_creation"
                        _log(f"Phase 1.5 — Qualification sans site ({len(without_site)} candidats)")

                        for lead in without_site:
                            if is_stop_requested():
                                break
                            _state["processed"] += 1
                            if _is_eligible_no_site(lead):
                                ok = _store_lead(
                                    lead, campaign_id, tag="creation", niveau=3,
                                    reason=f"Annonceur actif sans site — {lead.get('fan_count', 0)} abonnés"
                                )
                                if ok:
                                    _state["no_site"]  += 1
                                    _state["accepted"] += 1
                                    _log(f"  ✓  {lead.get('page_name', '?')} — création")
                                else:
                                    _state["errors"] += 1
                            else:
                                _state["rejected"] += 1

                    if not is_stop_requested() and with_site:
                        # — Phase 2/3 : Enrichissement + Scoring ─────────────
                        _state["phase"] = "enrichissement"
                        _log(f"Phase 2/3 — Enrichissement + Scoring ({len(with_site)} leads, {parallel} workers)")

                        from scraper.sniper.scoring import score_lead
                        executor = concurrent.futures.ThreadPoolExecutor(
                            max_workers=parallel, thread_name_prefix="fb-enrich"
                        )
                        futures = {executor.submit(_enrich_with_site, lead): lead for lead in with_site}
                        try:
                            for future in concurrent.futures.as_completed(futures):
                                if is_stop_requested():
                                    break
                                _state["processed"] += 1
                                lead = futures[future]
                                name = lead.get("page_name", "?")
                                try:
                                    enriched = future.result()
                                    if not enriched:
                                        _state["errors"] += 1
                                        continue
                                    result = score_lead(
                                        enriched.get("pagespeed",  {}),
                                        enriched.get("wappalyzer", {}),
                                        source="fb_ads",
                                    )
                                    if result is None:
                                        tag, niveau, reason = "rejete", 0, "Site performant ou pas d'urgence détectée"
                                        statut = "rejete"
                                    else:
                                        tag, niveau, reason = result
                                        statut = "en_attente"
                                        
                                    if enriched.get("_skip_reason"):
                                        tag, niveau, reason = "rejete", 0, enriched["_skip_reason"]
                                        statut = "rejete"
                                        
                                    ok = _store_lead(enriched, campaign_id, tag=tag, niveau=niveau, reason=reason, statut=statut)
                                    if ok:
                                        if statut == "en_attente":
                                            _state["accepted"] += 1
                                        else:
                                            _state["rejected"] += 1
                                        _log(f"  ✓  {name} — {tag} (niv.{niveau})")
                                    else:
                                        _state["errors"] += 1
                                except Exception as e:
                                    _state["errors"] += 1
                                    _log(f"  ! {name} — {type(e).__name__}: {e}", "warning")
                                    logger.error(f"[FB] Erreur enrichissement {name}: {traceback.format_exc()}")
                        finally:
                            executor.shutdown(wait=False, cancel_futures=True)

                # — Vérification quota + rotation ─────────────────────────────
                accepted_total = _state["accepted"]
                if min_leads > 0 and accepted_total < min_leads and rotator.has_more() and not is_stop_requested():
                    rotation_pass += 1
                    current_terms = rotator.next_batch_multi(original_terms, batch_size=3)
                    rotator.mark_used(current_terms)
                    _log(
                        f"  [{accepted_total}/{min_leads} leads] Rotation #{rotation_pass} —"
                        f" {len(current_terms)} nouvelles variantes"
                    )
                    continue
                break   # quota atteint ou rotation non demandée

            _log(
                f"Pipeline terminé — "
                f"{_state['accepted']} accepté(s) ({_state['no_site']} création), "
                f"{_state['rejected']} rejeté(s), {_state['errors']} erreur(s)"
                + (f" [rotation x{rotation_pass}]" if rotation_pass else "")
            )

            # ── Notification Telegram ─────────────────────────────────────────
            try:
                from core.telegram_adapter import notify
                notify(
                    f"🎯 *Scan FB Ads Terminé*\n"
                    f"📂 {campaign_name}\n"
                    f"✅ {_state['accepted']} leads acceptés\n"
                    f"❌ {_state['rejected']} rejetés\n"
                    f"⚠️ {_state['errors']} erreurs"
                )
            except Exception as e:
                logger.warning(f"[FB] Telegram notification failed: {e}")

            return self._result(campaign_id)

        except Exception as e:
            logger.error(f"[FB] ERREUR CRITIQUE: {traceback.format_exc()}")
            _log(f"ERREUR CRITIQUE : {type(e).__name__}: {e}", "error")
            return {"error": str(e), "campaign_id": campaign_id}

        finally:
            _state["running"]  = False
            _state["phase"]    = "done"
            _state["ended_at"] = datetime.now().isoformat()

    @staticmethod
    def _result(campaign_id) -> Dict:
        return {
            "accepted":    _state["accepted"],
            "rejected":    _state["rejected"],
            "no_site":     _state["no_site"],
            "errors":      _state["errors"],
            "campaign_id": campaign_id,
        }
