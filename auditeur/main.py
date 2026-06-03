# -*- coding: utf-8 -*-
"""
auditeur/main.py — Orchestrateur d'audit technique
Lit les leads depuis SQLite (source de vérité), lance l'analyse web,
et persiste les résultats dans SQLite.
"""
import os
import sys
import json
import time
import asyncio
import logging
from typing import Dict, Any, List
import argparse
import nest_asyncio
import signal
import threading

# Autorise l'imbrication des boucles d'événements (crucial pour l'intégration dashboard)
nest_asyncio.apply()

def safe_run_async(coro):
    """Exécute une coroutine en gérant les conflits de boucle."""
    try:
        loop = asyncio.get_event_loop()
        # Si la loop n'est pas en cours d'exécution, on peut l'utiliser normalement
        if not loop.is_running():
            if loop.is_closed():
                return asyncio.run(coro)
            return loop.run_until_complete(coro)

        # Si la loop est déjà running (ex: contexte async ou nest_asyncio), exécuter la coroutine
        # dans un thread séparé pour éviter les erreurs "already running" et permettre
        # aux primitives asyncio (Semaphore, wait_for, etc.) de fonctionner correctement.
        result = {}
        exc = {}

        def _runner():
            try:
                result['value'] = asyncio.run(coro)
            except Exception as e:
                exc['err'] = e

        t = threading.Thread(target=_runner)
        t.start()
        t.join()

        if 'err' in exc:
            raise exc['err']
        return result.get('value')
    except RuntimeError:
        # Fallback robuste
        return asyncio.run(coro)

# Ajout du dossier parent pour config_manager et database
current_dir = os.path.abspath(os.path.dirname(__file__))
root_dir    = os.path.abspath(os.path.join(current_dir, '..'))
sys.path.append(root_dir)

# Forcer l'encodage UTF-8 pour Windows
if sys.stdout.encoding.lower() != 'utf-8':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

from config_manager import get_sheet, check_daily_reset
from core.browser import close_all_browsers_sync

# --- Source de vérité SQLite ---
try:
    from database.db_manager import (
        get_leads_pending, insert_audit, update_lead_statut,
        get_lead_by_name, get_lead_by_id, init_db
    )
    _DB_AVAILABLE = True
except ImportError:
    _DB_AVAILABLE = False
    print("[WARN] database/db_manager.py introuvable — mode Sheets uniquement")

# Configuration du logger
logging.basicConfig(
    filename=os.path.join(root_dir, 'errors.log'),
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import des sous-agents techniques
from auditeur.agents.gmb_extractor import collect_gmb
from auditeur.agents.web_analyzer import run_web_analysis
from synthetiseur.mockup_generator import generate_mockup
from synthetiseur.vercel_publisher import publish_rapport


# ===========================================================
# AUDIT VIA SQLITE (mode principal)
# ===========================================================

def run_tech_audit_sqlite(limit=None, lead_names=None, lead_ids=None):
    """Audit depuis SQLite → SQLite (mode principal)."""
    if not _DB_AVAILABLE:
        print("   [!] SQLite non disponible, basculement sur Sheets.")
        run_tech_audit_sheets(limit)
        return

    if lead_ids:
        leads = []
        for lid in lead_ids:
            l = get_lead_by_id(lid)
            if l: leads.append(l)
    elif lead_names:
        leads = []
        for name in lead_names:
            l = get_lead_by_name(name)
            if l: leads.append(l)
    else:
        leads = get_leads_pending(verify_smtp=True)

    if not leads:
        print("   [!] Aucun lead à auditer.")
        return

    if limit:
        leads = leads[:limit]

    print(f"   [OK] {len(leads)} leads à auditer depuis SQLite.")
    processed = 0

    for lead in leads:
        try:
            lead_id  = lead['id']
            nom      = lead.get('nom', '')
            ville    = lead.get('ville', '')
            site_url = lead.get('site_web', '')

            print(f"\n--- Audit Technique de : {nom} ---")

            audit_result = {'lead_id': lead_id}
            try:
                gmb_data = collect_gmb(nom, ville, lead)
            except Exception as e_gmb:
                logger.error(f"Erreur GMB pour {nom}: {e_gmb}")
                print(f"   [WARN GMB] Échec de la collecte GMB : {e_gmb}")
                gmb_data = {}
            
            skip_analysis = False
            # Incohérence scraper : avertissement uniquement, audit continue
            if gmb_data.get('rating', 0) > 0 and gmb_data.get('nb_avis', 0) == 0:
                msg = f"Incohérence scraper : Note de {gmb_data.get('rating')} mais 0 avis."
                print(f"   [WARN GMB] {msg} -> Audit continue quand même.")
                logger.warning(f"Incohérence GMB pour {nom} (ID {lead_id}) : {msg}")

            audit_result.update(gmb_data)

            # 1. Analyse Web Technique avec retry
            max_retries = 3
            audit_success = False

            if not skip_analysis:
                if not (site_url and site_url.startswith(('http://', 'https://'))):
                    # Pas de site = Profil A (pas de retry nécessaire)
                    print(f"   [!] Pas de site web pour {nom} - Profil A")
                    audit_result['mobile_score'] = 0
                    audit_result['score_seo'] = 0
                    audit_result['score_urgence'] = 8.0
                    audit_success = True
                else:
                    for attempt in range(1, max_retries + 1):
                        print(f"   [Orchestrateur] Lancement de l'audit technique (tentative {attempt}/{max_retries})...")
                        try:
                            # Création du dossier temporaire pour les captures d'écran si nécessaire
                            report_dir = None
                            if lead.get('id'):
                                report_dir = f"data/reports/{lead['id']}"
                                os.makedirs(report_dir, exist_ok=True)
                                print(f"   [Orchestrateur] Dossier de rapport : {report_dir}")

                            web_results = safe_run_async(run_web_analysis(site_url, report_dir=report_dir))
                            audit_result.update(web_results)

                            # Détection rapide des erreurs réseau/connexion critiques
                            perf_err = audit_result.get('mobile_performance_error') or audit_result.get('desktop_performance_error')
                            if perf_err:
                                s_err = str(perf_err).lower()
                                if any(k in s_err for k in ('connect', 'dns', 'refused', 'reset', 'err_connection', 'connectivity')):
                                    print("   [Orchestrateur] [CRITICAL] Site inaccessible détecté -> nettoyage navigateurs et passage au lead suivant.")
                                    logger.warning(f"Site inaccessible détecté pour lead {lead_id} ({site_url}): {perf_err}")
                                    try:
                                        close_all_browsers_sync()
                                    except Exception as e_close:
                                        logger.warning(f"Erreur close_all_browsers_sync après détection inaccessible: {e_close}")
                                    # Marquer comme échec et sortir des tentatives
                                    audit_result['audit_failed'] = True
                                    audit_result['mobile_score'] = 0
                                    audit_result['score_seo'] = 0
                                    audit_result['score_urgence'] = 0
                                    break

                            # Vérification des données essentielles
                            mobile_score = audit_result.get('mobile_score')
                            performance_error = audit_result.get('mobile_performance_error')
                            
                            if mobile_score is not None and mobile_score > 0 and not performance_error:
                                print(f"   [Orchestrateur] [OK] Audit technique réussi (Score Mobile: {mobile_score})")
                                audit_success = True
                                break
                            else:
                                if performance_error:
                                    print(f"   [Orchestrateur] [WARN] Échec performance détecté : {performance_error}")
                                else:
                                    print(f"   [Orchestrateur] [WARN] Données incomplètes (tentative {attempt})")

                        except Exception as e:
                            logger.error(f"Erreur web analyzer pour {nom} (tentative {attempt}): {e}")
                            print(f"   [Orchestrateur] [ERROR] ÉCHEC critique : {e}")

                        if attempt < max_retries:
                            print(f"   [Orchestrateur] Pause 3s avant nouvelle tentative...")
                            time.sleep(3)
            
            # Si audit échoué après les tentatives — utiliser données partielles si disponibles
            if not audit_success and site_url:
                performance_error = audit_result.get('mobile_performance_error')
                partial_score = audit_result.get('mobile_score') or audit_result.get('desktop_score') or 0
                seo_partial = audit_result.get('has_meta_description') is not None or audit_result.get('has_https') is not None
                if performance_error:
                    print(f"   [ERREUR] Analyse technique échouée après {max_retries} tentatives : {performance_error}")
                    audit_result['mobile_score'] = 0
                    audit_result['score_seo'] = 0
                    audit_result['score_urgence'] = 0
                    audit_result['audit_failed'] = True
                elif partial_score > 0 or seo_partial:
                    # Don't use a score of 0 if failed, mark as partial
                    print(f"   [PARTIEL] Données partielles disponibles (score={partial_score}) — audit sauvegardé en mode dégradé")
                    audit_success = True
                    audit_result['audit_partial'] = True
                    if not audit_result.get('mobile_score'):
                        audit_result['mobile_score'] = partial_score
                else:
                    print(f"   [ERREUR] Échec de l'analyse après {max_retries} tentatives — aucune donnée exploitable")
                    audit_result['mobile_score'] = 0
                    audit_result['score_seo'] = 0
                    audit_result['score_urgence'] = 0
                    audit_result['audit_failed'] = True

            # Calcul des scores agrégés (si analyse réussie)
            if audit_success and site_url:
                mobile_score = audit_result.get('mobile_score', 0)
                seo_flags = [
                    bool(audit_result.get('has_https')),
                    bool(audit_result.get('has_meta_description')),
                    (audit_result.get('h1_count') or 0) > 0,
                    bool(audit_result.get('has_schema')),
                    bool(audit_result.get('has_contact_button')),
                ]
                score_seo = round(sum(seo_flags) / len(seo_flags) * 100)
                score_urgence = _calculer_score_urgence(mobile_score, score_seo)

                audit_result['score_performance'] = int(mobile_score)
                audit_result['score_seo']         = score_seo
                audit_result['score_urgence']      = score_urgence

                print(f"   [OK] Performance: {mobile_score} | SEO: {score_seo} | Urgence: {score_urgence}/10")
            
            # Déterminer le profil de l'entreprise
            # Priorité: audit_result (GMB extractor) > lead (scraper)
            rating = audit_result.get('rating') or lead.get('rating', 0) or 0
            reviews = audit_result.get('nb_avis') or lead.get('nb_avis', 0) or 0
            m_score = audit_result.get('mobile_score', 0) or 0
            lcp_ms = audit_result.get('lcp_ms', 0) or 0
            has_meta = audit_result.get('has_meta_description', False)
            has_schema = audit_result.get('has_schema', False)
            has_robots = audit_result.get('has_robots', False)
            has_sitemap = audit_result.get('has_sitemap', False)
            
            # Logique des profils (ordre de priorite):
            # 1. Pas de site -> Maquette (A)
            # 2. Site lent (m_score < 60 OU lcp >= 3000) -> Audit technique (B)
            # 3. Site OK mais SEO incomplet (!has_meta OR !has_schema OR !has_robots OR !has_sitemap) -> SEO (D)
            # 4. GMB mediochre (rating < 4.5 OU reviews < 50) -> Reputation (C)
            # 5. Tout OK -> Ignored
            
            # Verifier si l'audit a echoue
            if audit_result.get('audit_failed', False):
                print(f"   [ERREUR] Audit echoue apres {max_retries} tentatives - pas de rapport genere")
                audit_result['lien_rapport'] = None
                audit_result['template_used'] = 'failed'
                
            elif not site_url:
                # ===== PROFIL A (pas de site) =====
                print(f"   [Agent Reporter] Création du rapport HTML Profil A (maquette)...")
                mockup_result = generate_mockup(lead)
                audit_result.update(mockup_result)
                audit_result['template_used'] = 'maquette'
                try:
                    from reporter.main import generate_and_publish_report
                    lien_rapport = safe_run_async(generate_and_publish_report(audit_result))
                    audit_result['lien_rapport'] = lien_rapport
                    print(f"   [OK] Rapport Profil A (HTML) publié: {lien_rapport}")
                except Exception as e:
                    logger.error(f"Erreur HTML pour {nom}: {e}")
                    print(f"   [ERREUR] HTML: {e}")
            
            elif m_score < 60 or lcp_ms >= 3000:
                # ===== AUDIT TECHNIQUE (site avec problemes de performance) =====
                print(f"   [Agent Reporter] Generation rapport HTML Technique... (score={m_score}, lcp={lcp_ms}ms)")
                audit_result['template_used'] = 'audit'
                audit_result['rating'] = rating
                audit_result['reviews_count'] = reviews
                audit_result['category'] = lead.get('category', lead.get('secteur', 'Entreprise'))
                audit_result['ville'] = lead.get('ville', '')
                
                try:
                    from reporter.main import generate_and_publish_report
                    print(f"   [Reporter] Lancement de la génération HTML pour {nom}...")
                    lien_rapport = safe_run_async(generate_and_publish_report(audit_result))
                    audit_result['lien_rapport'] = lien_rapport
                    print(f"   [Reporter] [OK] Rapport publié : {lien_rapport}")
                except Exception as e:
                    logger.error(f"Erreur Technique HTML pour {nom}: {e}")
                    print(f"   [Reporter] [ERROR] ÉCHEC génération HTML : {e}")
            
            elif not has_meta or not has_schema or not has_robots or not has_sitemap:
                # ===== SEO (site OK en performance mais problemes SEO) =====
                print(f"   [Agent Reporter] Generation rapport HTML SEO...")
                audit_result['template_used'] = 'seo'
                audit_result['rating'] = rating
                audit_result['reviews_count'] = reviews
                audit_result['category'] = lead.get('category', lead.get('secteur', 'Entreprise'))
                audit_result['ville'] = lead.get('ville', '')
                
                try:
                    from reporter.main import generate_and_publish_report
                    lien_rapport = safe_run_async(generate_and_publish_report(audit_result))
                    audit_result['lien_rapport'] = lien_rapport
                    print(f"   [OK] Rapport SEO (HTML) public: {lien_rapport}")
                except Exception as e:
                    logger.error(f"Erreur SEO HTML pour {nom}: {e}")
                    print(f"   [ERREUR] SEO HTML: {e}")
                    audit_result['lien_rapport'] = None
            
            elif rating < 4.5 or reviews < 50:
                # ===== REPUTATION (fiche GMB à améliorer) =====
                print(f"   [Agent Reporter] Génération rapport HTML Réputation (Note={rating}, Avis={reviews})...")
                audit_result['template_used'] = 'reputation'
                audit_result['profile'] = 'C'
                
                audit_result['rating'] = rating
                audit_result['reviews_count'] = reviews
                audit_result['category'] = lead.get('category', lead.get('secteur', 'Entreprise'))
                audit_result['ville'] = lead.get('ville', '')
                
                try:
                    from reporter.main import generate_and_publish_report
                    lien_rapport = safe_run_async(generate_and_publish_report(audit_result))
                    audit_result['lien_rapport'] = lien_rapport
                    print(f"   [OK] Rapport Réputation (HTML) publié: {lien_rapport}")
                except Exception as e:
                    logger.error(f"Erreur Réputation HTML pour {nom}: {e}")
                    print(f"   [ERREUR] Réputation HTML: {e}")
            
            elif rating >= 4.5 and reviews >= 50 and m_score >= 60 and lcp_ms < 3000 and has_meta:
                # ===== IGNORED (tout va bien) =====
                print(f"   [IGNORER] Entreprise OK: site={m_score}/100, GMB={rating}/5 ({reviews} avis)")
                audit_result['lien_rapport'] = None
                audit_result['template_used'] = 'ignored'
            
            else:
                # ===== FALLBACK (cas limite) =====
                print(f"   [Agent Reporter] Génération rapport HTML Technique (fallback)...")
                audit_result['template_used'] = 'audit'
                audit_result['rating'] = rating
                audit_result['reviews_count'] = reviews
                audit_result['category'] = lead.get('category', lead.get('secteur', 'Entreprise'))
                audit_result['ville'] = lead.get('ville', '')
                
                try:
                    from reporter.main import generate_and_publish_report
                    lien_rapport = safe_run_async(generate_and_publish_report(audit_result))
                    audit_result['lien_rapport'] = lien_rapport
                    print(f"   [OK] Rapport Technique (HTML) publié: {lien_rapport}")
                except Exception as e:
                    logger.error(f"Erreur Technique HTML pour {nom}: {e}")
                    print(f"   [ERREUR] Technique HTML: {e}")
            
            # 3. Persistance dans SQLite
            try:
                print(f"   [SQLite] Sauvegarde de l'audit ID {lead_id}...")
                # DEBUG: dump audit_result to verify fields before persisting
                try:
                    print("   [DEBUG] audit_result keys:", list(audit_result.keys()))
                    small = {k: (audit_result[k] if k in ('mobile_score','desktop_score','score_seo','score_urgence','lien_rapport','template_used') else '...') for k in audit_result}
                    print("   [DEBUG] audit_result preview:", small)
                except Exception:
                    pass

                # Normalize/force numeric score fields before DB insert to avoid NULL/'' issues
                try:
                    def _to_int(v, default=0):
                        if v is None or v == '':
                            return default
                        try:
                            return int(float(v))
                        except Exception:
                            return default

                    def _to_float(v, default=0.0):
                        if v is None or v == '':
                            return default
                        try:
                            return float(v)
                        except Exception:
                            return default

                    audit_result['mobile_score'] = _to_int(audit_result.get('mobile_score'))
                    audit_result['desktop_score'] = _to_int(audit_result.get('desktop_score'))
                    # backward-compatible performance field
                    audit_result['score_performance'] = _to_int(audit_result.get('score_performance') or audit_result.get('mobile_score'))
                    audit_result['score_seo'] = _to_int(audit_result.get('score_seo'))
                    audit_result['score_urgence'] = _to_float(audit_result.get('score_urgence', 0.0))
                    # timing fields
                    if 'lcp_ms' not in audit_result or not audit_result.get('lcp_ms'):
                        audit_result['lcp_ms'] = _to_float(audit_result.get('mobile_lcp_ms'))
                    audit_result['fcp_ms'] = _to_float(audit_result.get('mobile_fcp_ms'))
                except Exception as e:
                    logger.warning(f"Normalization before insert failed: {e}")

                insert_audit(audit_result)
                # Déterminer le statut final
                if audit_result.get('audit_failed', False):
                    final_statut = 'audit_echoue'
                    print(f"   [SQLite] [ERROR] Audit marqué comme ÉCHOUÉ pour {nom}")
                else:
                    final_statut = 'audite'
                    print(f"   [SQLite] [OK] Audit enregistré avec succès pour {nom}")
                update_lead_statut(lead_id, final_statut)
            except Exception as e:
                logger.error(f"Erreur insert_audit({nom}): {e}")
                print(f"   [SQLite] [ERROR] ÉCHEC sauvegarde : {e}")
            
            # 4. Génération automatique de l'email après audit réussi
            if not audit_result.get('audit_failed', False) and audit_result.get('template_used') not in ('ignored', 'failed'):
                try:
                    print(f"   [Email Generator] Génération de l'email pour {nom}...")
                    from services.email_generator import generate_email_for_lead
                    if generate_email_for_lead(lead_id):
                        print(f"   [Email Generator] [OK] Email généré et stocké pour {nom}")
                    else:
                        logger.warning(f"Email generation échoue pour {nom} (lead_id={lead_id})")
                        print(f"   [Email Generator] [WARN] Impossible de générer l'email")
                except Exception as e:
                    logger.error(f"Erreur email_generator pour {nom}: {e}")
                    print(f"   [Email Generator] [ERROR] {e}")

        except Exception as global_e:
            import traceback
            trace = traceback.format_exc()
            logger.error(f"Crash inattendu de l'audit pour le lead ID {lead.get('id', 'inconnu')} : {global_e}\n{trace}")
            print(f"   [CRITICAL ERROR] Le traitement a échoué pour {lead.get('nom', 'Inconnu')} : {global_e}")
            try:
                if lead.get('id'):
                    update_lead_statut(lead['id'], 'audit_echoue')
            except:
                pass
            
            print("   [RECOVERY] Nettoyage des navigateurs zombies et pause de 5s pour stabiliser le système avant de continuer...")
            try:
                close_all_browsers_sync()
            except Exception as e_close:
                print(f"   [RECOVERY] Erreur lors de la fermeture des navigateurs : {e_close}")
            time.sleep(5)

        processed += 1
        if limit and processed >= limit:
            break

        # Délai pour ménager les quotas d'API
        time.sleep(3)

    print(f"\n[Terminé] Audit SQLite terminé pour {processed} lead(s).")


def _calculer_score_urgence(performance_score: float, seo_score: float) -> float:
    """
    Score d'urgence 0-10 : plus le site est mauvais, plus le score est élevé.
    Un score élevé = prospect prioritaire à contacter.
    """
    # Gestion des valeurs None (échec de scan)
    if performance_score is None: performance_score = 50.0
    if seo_score is None: seo_score = 50.0

    # Performance faible = urgence haute (inverse)
    perf_urgence = (100 - performance_score) / 100 * 6  # Poids 60%
    # SEO faible = aussi urgent
    seo_urgence  = (100 - seo_score) / 100 * 4          # Poids 40%
    return round(perf_urgence + seo_urgence, 1)


# ===========================================================
# AUDIT VIA SHEETS (mode fallback)
# ===========================================================

def run_tech_audit_sheets(limit=None):
    """Audit legacy depuis Google Sheets (mode fallback)."""
    sheet = get_sheet("Leads")
    all_rows = sheet.get_all_values()
    if not all_rows:
        print("   [!] Feuille vide.")
        return

    headers = all_rows[0]

    # Vérification des colonnes nécessaires
    cols_to_check = ["Nom", "Ville", "Site Web", "Résultats Technique", "JSON Complet"]
    for col in cols_to_check:
        if col not in headers:
            print(f"   [!] Colonne manquante : {col}")
            return

    processed = 0
    for i, row in enumerate(all_rows[1:]):
        row_num = i + 2
        data = dict(zip(headers, row))

        if not data.get("Résultats Technique"):
            nom      = data.get("Nom") or data.get("nom")
            ville    = data.get("Ville") or data.get("ville")
            site_url = data.get("Site Web") or data.get("site_web")

            print(f"\n--- Audit Technique de : {nom} ---")

            try:
                full_data = json.loads(data.get("JSON Complet", "{}"))
            except:
                full_data = {}

            full_data["nom"]      = nom
            full_data["ville"]    = ville
            full_data["site_web"] = site_url

            if site_url and "http" in site_url:
                print(f"   [Agent Web] Analyse technique de {site_url}...")
                try:
                    web_results = safe_run_async(run_web_analysis(site_url))
                    full_data.update(web_results)
                    res_tech = f"Mobile: {web_results.get('mobile_score')}/100"
                except Exception as e:
                    logger.error(f"Erreur web analyzer pour {nom}: {e}")
                    res_tech = "ERREUR TECH"
            else:
                full_data["mobile_score"] = 0
                res_tech = "SANS SITE"

            # Sauvegarde dans Google Sheets
            col_tech = headers.index("Résultats Technique") + 1
            col_json = headers.index("JSON Complet") + 1
            sheet.update_cell(row_num, col_tech, res_tech)
            sheet.update_cell(row_num, col_json, json.dumps(full_data, ensure_ascii=False))

            # Aussi sauvegarder dans SQLite si disponible
            if _DB_AVAILABLE:
                lead = get_lead_by_name(nom)
                if lead:
                    full_data['lead_id'] = lead['id']
                    try:
                        insert_audit(full_data)
                        update_lead_statut(lead['id'], 'audite')
                    except Exception as e:
                        logger.error(f"SQLite insert_audit({nom}): {e}")

            processed += 1
            if limit and processed >= limit:
                break

            time.sleep(3)

    print(f"\n[Terminé] Audit Sheets terminé pour {processed} lead(s).")


# ===========================================================
# POINT D'ENTRÉE
# ===========================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                        help="Nombre max de leads à auditer")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simulation sans écriture")
    parser.add_argument("--sheets", action="store_true",
                        help="Forcer le mode Sheets (legacy)")
    parser.add_argument("--leads", nargs="+",
                        help="Noms des leads à auditer spécifiquement")
    parser.add_argument("--ids", type=int, nargs="+",
                        help="IDs des leads à auditer spécifiquement")
    args = parser.parse_args()

    check_daily_reset()

    try:
        if args.sheets:
            run_tech_audit_sheets(limit=args.limit)
        else:
            run_tech_audit_sqlite(limit=args.limit, lead_names=args.leads, lead_ids=args.ids)
    finally:
        close_all_browsers_sync()
