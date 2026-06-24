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
from synthetiseur.mockup_generator import generate_mockup


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

    # Ne traiter que les leads sans site web.
    leads = [
        lead for lead in leads
        if not (lead.get('site_web') or '').strip().lower().startswith(('http://', 'https://'))
    ]
    if not leads:
        print("   [!] Aucun lead sans site web à auditer.")
        return

    print(f"   [OK] {len(leads)} leads sans site à auditer depuis SQLite.")
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

            # 1. Audit no-site uniquement
            audit_success = False
            if site_url and site_url.strip().lower().startswith(('http://', 'https://')):
                print(f"   [SKIP] Lead avec site web détecté : {site_url} - traitement no-site uniquement.")
                audit_result['audit_failed'] = True
                audit_result['lien_rapport'] = None
                audit_result['template_used'] = 'ignored'
            else:
                print(f"   [OK] Pas de site web pour {nom} - Profil A")
                audit_result['mobile_score'] = 0
                audit_result['score_seo'] = 0
                audit_result['score_urgence'] = 8.0
                audit_success = True
            
            # Déterminer le profil de l'entreprise
            # Priorité: audit_result (GMB extractor) > lead (scraper)
            rating = audit_result.get('rating') or lead.get('rating', 0) or 0
            reviews = audit_result.get('nb_avis') or lead.get('nb_avis', 0) or 0

            # Verifier si l'audit a echoue
            if audit_result.get('audit_failed', False):
                print(f"   [ERREUR] Audit échoué - pas de rapport généré")
                audit_result['lien_rapport'] = None
                audit_result['template_used'] = 'failed'

            elif not site_url or not site_url.strip():
                # ===== PROFIL A (pas de site) =====
                print(f"   [Agent Reporter] Création du rapport HTML Profil A (maquette)...")
                mockup_result = generate_mockup(lead)
                audit_result.update(mockup_result)
                audit_result['template_used'] = 'maquette'
                lien_rapport = None
                try:
                    from reporter.main import generate_and_publish_report
                    lien_rapport = safe_run_async(generate_and_publish_report(audit_result))
                    audit_result['lien_rapport'] = lien_rapport
                    print(f"   [OK] Rapport Profil A (HTML) généré: {lien_rapport}")
                except Exception as e:
                    logger.error(f"Erreur HTML pour {nom}: {e}")
                    print(f"   [ERREUR] HTML: {e}")

                # ── Publication automatique sur GitHub Pages ──
                if lien_rapport and lien_rapport.startswith("local://"):
                    slug = lien_rapport.replace("local://", "").strip("/")
                    try:
                        from dashboard.pipeline.report_publishing import publish_reports_batch
                        public_url = publish_reports_batch([slug])
                        if public_url:
                            audit_result['lien_rapport'] = public_url
                            print(f"   [OK] Rapport publié sur GitHub : {public_url}")
                        else:
                            print(f"   [WARN] Publication GitHub échouée pour {slug}, lien local conservé")
                    except Exception as e:
                        logger.error(f"Erreur publication GitHub pour {slug}: {e}")
                        print(f"   [ERROR] Publication GitHub : {e}")

            else:
                print(f"   [SKIP] Lead avec site web ignoré par le module no-site.")
                audit_result['lien_rapport'] = None
                audit_result['template_used'] = 'ignored'
            
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

            if site_url and site_url.strip().lower().startswith(('http://', 'https://')):
                print(f"   [SKIP] Lead avec site web détecté en Sheets : {site_url} - traitement no-site uniquement.")
                full_data["mobile_score"] = 0
                res_tech = "SANS SITE"
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
