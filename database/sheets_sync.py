# -*- coding: utf-8 -*-
"""
database/sheets_sync.py — Synchronisation SQLite <-> Google Sheets (miroir)
- import_from_sheets() : migration one-shot depuis Sheets vers SQLite
- sync_to_sheets()     : SQLite → Sheets (miroir toutes les heures)
"""

import os
import sys
import json
import logging
import argparse
from pathlib import Path
from datetime import datetime

# Ajout du dossier parent au path pour accéder à config_manager
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.db_manager import (
    get_conn, insert_lead, insert_audit, init_db, log_sync,
    get_conn
)
from config_manager import get_sheet

# --- Logging ---
logging.basicConfig(
    filename=str(Path(__file__).parent.parent / "errors.log"),
    level=logging.ERROR,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ===========================================================
# HELPERS INTERNES
# ===========================================================

def _safe_float(val, default=0.0):
    """Conversion sécurisée en float."""
    try:
        return float(val) if val not in (None, '', 'N/A', 'N/A', '-') else default
    except (ValueError, TypeError):
        return default

def _safe_int(val, default=0):
    """Conversion sécurisée en int."""
    try:
        return int(float(val)) if val not in (None, '', 'N/A', '-') else default
    except (ValueError, TypeError):
        return default

def _safe_bool(val):
    """Conversion sécurisée en booléen."""
    return str(val).strip().upper() in ('TRUE', '1', 'OUI', 'YES', '✓')


# ===========================================================
# IMPORT INITIAL: SHEETS → SQLITE
# ===========================================================

def import_from_sheets() -> dict:
    """
    Migration one-shot depuis Google Sheets → SQLite.
    Lit la feuille "Leads" principale et insère dans leads_bruts.
    Lit aussi les colonnes d'audit si elles contiennent des données.
    """
    summary = {'leads_importes': 0, 'audits_importes': 0, 'erreurs': 0}

    print("\n📥 Import depuis Google Sheets → SQLite...")

    try:
        # ── 1. Feuille "Leads" principale (scraper) ──
        try:
            sheet_leads = get_sheet("Leads")
            all_rows = sheet_leads.get_all_records()
            print(f"   Feuille 'Leads' : {len(all_rows)} lignes trouvées")
        except Exception as e:
            print(f"   [WARN] Feuille 'Leads' inaccessible : {e}")
            all_rows = []

        for row in all_rows:
            try:
                nom = str(row.get('Nom', row.get('nom', ''))).strip()
                if not nom:
                    continue

                lead_data = {
                    'nom':          nom,
                    'adresse':      str(row.get('Adresse', row.get('adresse', ''))),
                    'site_web':     str(row.get('Site Web', row.get('site_web', ''))),
                    'telephone':    str(row.get('Téléphone', row.get('telephone', ''))),
                    'email':        str(row.get('Email', row.get('email', ''))),
                    'email_valide': str(row.get('Statut Email', '')),
                    'rating':       _safe_float(row.get('Note Maps', row.get('rating', 0))),
                    'nb_avis':      _safe_int(row.get('Avis Maps', row.get('nb_avis', 0))),
                    'category':     str(row.get('Catégorie', row.get('category', ''))),
                    'mot_cle':      str(row.get('Mot-clé', row.get('mot_cle', ''))),
                    'ville':        str(row.get('Ville', row.get('ville', ''))),
                    'lien_maps':    str(row.get('Lien Maps', row.get('lien_maps', ''))),
                    'statut_email': str(row.get('Statut Email', '')),
                }

                lead_id = insert_lead(lead_data)

                # ── Données d'audit dans le JSON Complet ──
                json_complet = row.get('JSON Complet', '')
                audit_data = {}
                if json_complet:
                    try:
                        audit_data = json.loads(json_complet)
                    except Exception:
                        pass

                # Colonnes d'audit directes (si remplies)
                col_tech = str(row.get('Résultats Technique', ''))
                email_objet = str(row.get('Objet Email', audit_data.get('email_objet', '')))
                email_corps = str(row.get('Corps Email', audit_data.get('email_corps', '')))
                probleme    = str(row.get('Problèmes Détectés', audit_data.get('probleme_principal', '')))
                service     = str(row.get('Service Proposé', audit_data.get('service_suggere', '')))
                lien_rapport = str(row.get('Lien Rapport PDF', row.get('Lien Rapport', audit_data.get('lien_rapport', ''))))

                # Si des données d'audit sont disponibles, insérer
                has_audit_data = (
                    col_tech or email_objet or email_corps or
                    audit_data.get('mobile_score') or audit_data.get('score_urgence')
                )

                if has_audit_data:
                    full_audit = {
                        'lead_id':          lead_id,
                        'mobile_score':     _safe_int(audit_data.get('mobile_score', 0)),
                        'desktop_score':    _safe_int(audit_data.get('desktop_score', 0)),
                        'tablet_score':     _safe_int(audit_data.get('tablet_score', 0)),
                        'lcp_ms':           _safe_float(audit_data.get('lcp_ms', audit_data.get('mobile_lcp_ms', 0))),
                        'fcp_ms':           _safe_float(audit_data.get('fcp_ms', 0)),
                        'cls':              _safe_float(audit_data.get('cls', 0)),
                        'render_blocking_scripts': _safe_int(audit_data.get('render_blocking_scripts', 0)),
                        'uses_cache':       _safe_bool(audit_data.get('uses_cache', False)),
                        'page_size_kb':     _safe_float(audit_data.get('page_size_kb', 0)),
                        'has_https':        _safe_bool(audit_data.get('has_https', False)),
                        'has_meta_description': _safe_bool(audit_data.get('has_meta_description', False)),
                        'title_length':     _safe_int(audit_data.get('title_length', 0)),
                        'h1_count':         _safe_int(audit_data.get('h1_count', 0)),
                        'has_schema':       _safe_bool(audit_data.get('has_schema', False)),
                        'has_contact_button': _safe_bool(audit_data.get('has_contact_button', False)),
                        'tel_link':         _safe_bool(audit_data.get('tel_link', False)),
                        'images_without_alt': _safe_int(audit_data.get('images_without_alt', 0)),
                        'has_analytics':    _safe_bool(audit_data.get('has_analytics', False)),
                        'has_robots':       _safe_bool(audit_data.get('has_robots', False)),
                        'has_sitemap':      _safe_bool(audit_data.get('has_sitemap', False)),
                        'has_responsive_meta': _safe_bool(audit_data.get('has_responsive_meta', False)),
                        'cms_detected':     audit_data.get('cms_detected', ''),
                        'visible_text_words': _safe_int(audit_data.get('visible_text_words', 0)),
                        'score_performance': _safe_int(audit_data.get('score_performance', audit_data.get('mobile_score', 0))),
                        'score_seo':        _safe_int(audit_data.get('score_seo', 0)),
                        'score_gmb':        _safe_int(audit_data.get('score_gmb', 0)),
                        'score_urgence':    _safe_float(audit_data.get('score_urgence', audit_data.get('score_priorite', 0))),
                        'top3_problems':    audit_data.get('top3_problems', []),
                        'service_suggere':  service or audit_data.get('service_suggere', ''),
                        'probleme_principal': probleme or audit_data.get('probleme_principal', ''),
                        'arguments':        audit_data.get('arguments', []),
                        'rapport_resume':   audit_data.get('rapport_resume', ''),
                        'email_objet':      email_objet,
                        'email_corps':      email_corps,
                        'approuve':         _safe_bool(audit_data.get('approuve', False)),
                        'lien_rapport':     lien_rapport or audit_data.get('lien_rapport', ''),
                        'lien_pdf':         audit_data.get('lien_pdf', ''),
                    }
                    insert_audit(full_audit)

                    # Mettre à jour statut du lead
                    with get_conn() as conn:
                        conn.execute(
                            "UPDATE leads_bruts SET statut='audite' WHERE id=?",
                            (lead_id,)
                        )
                    summary['audits_importes'] += 1

                summary['leads_importes'] += 1

            except Exception as e:
                logger.error(f"Erreur import ligne {row}: {e}")
                summary['erreurs'] += 1

        # ── 2. Feuille "leads_audites" séparée (si elle existe) ──
        try:
            sheet_audits = get_sheet("leads_audites")
            audit_rows = sheet_audits.get_all_records()
            if audit_rows:
                print(f"   Feuille 'leads_audites' : {len(audit_rows)} lignes trouvées")
                for row in audit_rows:
                    nom = str(row.get('nom', '')).strip()
                    if not nom:
                        continue
                    with get_conn() as conn:
                        lead = conn.execute(
                            "SELECT id FROM leads_bruts WHERE LOWER(nom)=LOWER(?) LIMIT 1",
                            (nom,)
                        ).fetchone()
                        if lead:
                            audit_data = {
                                'lead_id':          lead['id'],
                                'mobile_score':     _safe_int(row.get('score_performance', row.get('mobile_score', 0))),
                                'desktop_score':    _safe_int(row.get('desktop_score', 0)),
                                'tablet_score':     _safe_int(row.get('tablet_score', 0)),
                                'lcp_ms':           _safe_float(row.get('lcp', row.get('lcp_ms', 0))),
                                'score_performance': _safe_int(row.get('score_performance', 0)),
                                'score_seo':        _safe_int(row.get('score_seo', 0)),
                                'score_urgence':    _safe_float(row.get('score_urgence', 0)),
                                'email_objet':      str(row.get('email_objet', '')),
                                'email_corps':      str(row.get('email_corps', '')),
                                'lien_rapport':     str(row.get('lien_rapport', '')),
                                'approuve':         _safe_bool(row.get('approuve', False)),
                                'probleme_principal': str(row.get('probleme_principal', '')),
                                'service_suggere':  str(row.get('service_suggere', '')),
                            }
                            insert_audit(audit_data)
                            summary['audits_importes'] += 1
        except Exception as e:
            print(f"   [INFO] Feuille 'leads_audites' inaccessible ou vide : {e}")

        # Log sync
        log_sync('all', 'sheets_to_sqlite', summary['leads_importes'])

        print(f"\n✅ Import terminé :")
        print(f"   Leads importés  : {summary['leads_importes']}")
        print(f"   Audits importés : {summary['audits_importes']}")
        print(f"   Erreurs         : {summary['erreurs']}")

    except Exception as e:
        logger.error(f"import_from_sheets → {e}")
        print(f"❌ Erreur import : {e}")

    return summary


# ===========================================================
# SYNC: SQLITE → SHEETS (miroir)
# ===========================================================

def sync_to_sheets() -> dict:
    """
    Synchronise SQLite → Google Sheets (toutes les heures).
    Écrase les données Sheets avec SQLite.
    """
    summary = {'tables_synced': 0, 'erreurs': 0}
    print(f"\n📤 Sync SQLite → Sheets ({datetime.now().strftime('%H:%M:%S')})...")

    try:
        # Connexion aux deux Sheets principaux
        sheet_leads   = get_sheet("leads_bruts")
        sheet_audites = get_sheet("leads_audites")
        sheet_emails  = get_sheet("emails_envoyes")

        with get_conn() as conn:

            # ── leads_bruts ──
            rows = conn.execute("""
                SELECT nom, ville, category, site_web, telephone,
                       email, email_valide, rating, nb_avis,
                       statut, date_scraping
                FROM leads_bruts
                ORDER BY date_scraping DESC LIMIT 500
            """).fetchall()
            _write_sheet(sheet_leads, [dict(r) for r in rows], "leads_bruts")
            summary['tables_synced'] += 1

            # ── leads_audites ──
            rows = conn.execute("""
                SELECT lb.nom, lb.ville, lb.category,
                       la.mobile_score, la.desktop_score,
                       la.score_seo, la.score_urgence,
                       la.lcp_ms, la.cms_detected,
                       la.email_objet, la.approuve,
                       la.lien_rapport, la.date_audit
                FROM leads_audites la
                JOIN leads_bruts lb ON lb.id = la.lead_id
                ORDER BY la.score_urgence DESC LIMIT 500
            """).fetchall()
            _write_sheet(sheet_audites, [dict(r) for r in rows], "leads_audites")
            summary['tables_synced'] += 1

            # ── emails_envoyes ──
            rows = conn.execute("""
                SELECT lb.nom, lb.email,
                       ee.date_envoi, ee.email_objet,
                       ee.ouvert, ee.repondu,
                       ee.type_reponse, ee.rdv_confirme,
                       ee.notes, ee.statut_envoi
                FROM emails_envoyes ee
                JOIN leads_bruts lb ON lb.id = ee.lead_id
                ORDER BY ee.date_envoi DESC LIMIT 300
            """).fetchall()
            _write_sheet(sheet_emails, [dict(r) for r in rows], "emails_envoyes")
            summary['tables_synced'] += 1

        log_sync('all', 'sqlite_to_sheets',
                 summary['tables_synced'], statut='ok')
        print(f"✅ Sync Sheets terminée ({summary['tables_synced']} tables)")

    except Exception as e:
        logger.error(f"sync_to_sheets → {e}")
        log_sync('all', 'sqlite_to_sheets', 0, statut='erreur', erreur=str(e))
        print(f"❌ Erreur sync Sheets : {e}")
        summary['erreurs'] += 1

    return summary


def _write_sheet(sheet, rows: list, name: str):
    """Réécrit une feuille Google Sheets complète."""
    try:
        sheet.clear()
        if not rows:
            print(f"   [{name}] Feuille vidée (aucune donnée).")
            return
        
        headers = list(rows[0].keys())
        values = [headers] + [
            [str(r.get(h, '')) for h in headers] for r in rows
        ]
        sheet.update(values=values, range_name='A1')
        print(f"   [{name}] {len(rows)} lignes synchronisées.")
    except Exception as e:
        logger.warning(f"_write_sheet({name}) → {e}")
        print(f"   [{name}] Erreur écriture : {e}")


# ===========================================================
# POINT D'ENTRÉE
# ===========================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Synchronisation SQLite <-> Google Sheets")
    parser.add_argument("--import", dest="do_import", action="store_true",
                        help="Importer depuis Sheets → SQLite (migration initiale)")
    parser.add_argument("--export", dest="do_export", action="store_true",
                        help="Exporter SQLite → Sheets (sync manuelle)")
    args = parser.parse_args()

    init_db()

    if args.do_import:
        import_from_sheets()
    if args.do_export:
        sync_to_sheets()
    if not args.do_import and not args.do_export:
        print("Usage:")
        print("  python sheets_sync.py --import   (Sheets → SQLite)")
        print("  python sheets_sync.py --export   (SQLite → Sheets)")
