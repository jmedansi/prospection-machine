# -*- coding: utf-8 -*-
"""
dashboard/app.py â Serveur Flask du cockpit Incidenx
SQLite comme source de vÃ©ritÃ© principale.
Sheets est synchronisÃ© toutes les heures en arriÃ¨re-plan.
Lance : python dashboard/app.py
Port  : 5001
"""

import os
import sys
import json
import logging
import subprocess
import threading
import time
import re
from datetime import datetime
# --- AccÃ¨s aux modules du projet ---
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from flask import Flask, jsonify, request, send_from_directory, abort, redirect
from dotenv import load_dotenv
# Chargement ultra-prÃ©coce du .env
env_path = os.path.join(ROOT, ".env")
print(f"  [Debug] Recherche .env dans : {env_path}")
print(f"  [Debug] Fichier existe : {os.path.exists(env_path)}")
load_dotenv(env_path)

from config_manager import get_sheet, logger

# --- SQLite (source de vÃ©ritÃ© principale) ---
from database.db_manager import (
    get_dashboard_stats, get_leads_for_dashboard,
    get_emails_for_dashboard, get_crm_data,
    get_audits_with_reports, update_crm_manual,
    insert_email_sent, update_audit_approval,
    update_email_tracking, get_audits_ready_for_email,
    init_db, delete_lead, update_lead, update_audit_email_content,
    get_conn, insert_campaign, get_all_campaigns, get_campaign_by_id,
    delete_campaign
)

# Initialisation automatique de la base au dÃ©marrage
init_db()

# --- Configuration Flask ---
app = Flask(__name__, static_folder=os.path.dirname(os.path.abspath(__file__)), static_url_path='')

# --- Logging (un seul appel, au niveau WARNING pour les erreurs)
logging.basicConfig(
    filename=os.path.join(ROOT, 'errors.log'),
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# âââââââââââââââââââââââââââââââââââââââââââââââ
# WEBHOOK RESEND - TRACKING DES EMAILS
# âââââââââââââââââââââââââââââââââââââââââââââââ

import hmac
import hashlib

# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# UTILITAIRES
# âââââââââââââââââââââââââââââââââââââââââââââââ

def _safe_int(val, default=0):
    """Convertit une valeur en entier, retourne default si impossible."""
    try:
        return int(val) if val not in (None, '', 'N/A', 0) else default
    except (ValueError, TypeError):
        return default

def _safe_float(val, default=0.0):
    """Convertit une valeur en float, retourne default si impossible."""
    try:
        return float(val) if val not in (None, '', 'N/A') else default
    except (ValueError, TypeError):
        return default

def _determine_profile_v9(audit_data: dict) -> str:
    """Determine le profil A, B, C, D ou I selon les regles de l'auditeur.
    
    Ordre de priorite:
    1. Maquette (pas de site) -> A
    2. Audit (performance: m_score < 60 OR lcp >= 3000) -> B
    3. SEO (!has_meta OR !has_schema OR !has_robots OR !has_sitemap) -> D
    4. Reputation (GMB: rating < 4.5 OR reviews < 50) -> C
    5. Ignored (tout OK) -> I
    """
    template_used = audit_data.get('template_used', '')
    has_site = bool(audit_data.get('site_web'))
    rating = _safe_float(audit_data.get('rating', 0))
    reviews = _safe_int(audit_data.get('nb_avis', audit_data.get('reviews_count', 0)))
    lcp_ms = _safe_int(audit_data.get('lcp_ms', 0))
    mobile_score = _safe_int(audit_data.get('mobile_score', audit_data.get('score_performance', 0)))
    has_meta = audit_data.get('has_meta_description', True)
    has_schema = audit_data.get('has_schema', True)
    has_robots = audit_data.get('has_robots', True)
    has_sitemap = audit_data.get('has_sitemap', True)
    audit_failed = audit_data.get('audit_failed', False)
    
    if template_used == 'maquette':
        return "A"
    if template_used == 'seo':
        return "D"
    if template_used == 'reputation':
        return "C"
    if template_used == 'audit':
        return "B"
    if template_used == 'ignored':
        return "I"
    if template_used == 'failed':
        return "F"
    
    if not has_site:
        return "A"
    if audit_failed:
        return "F"
    if mobile_score < 60 or lcp_ms >= 3000:
        return "B"
    if not has_meta or not has_schema or not has_robots or not has_sitemap:
        return "D"
    if rating < 4.5 or reviews < 50:
        return "C"
    return "I"


# âââââââââââââââââââââââââââââââââââââââââââââââ
# ROUTE PRINCIPALE â Sert le HTML
# âââââââââââââââââââââââââââââââââââââââââââââââ

@app.route('/')
def index():
    """Sert le fichier dashboard-v4.html avec headers no-cache."""
    dashboard_dir = os.path.dirname(os.path.abspath(__file__))
    response = send_from_directory(dashboard_dir, 'dashboard-v4.html')
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response

@app.after_request
def add_header(response):
    """Désactive le cache globalement."""
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# PREVIEWS LOCAUX - Nouveau workflow local-first
# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

@app.route('/previews/<slug>/<path:filename>')
def serve_preview_file(slug, filename):
    """Sert les fichiers (images) depuis le dossier local du rapport."""
    preview_dir = os.path.join(ROOT, 'reporter', 'reports', slug)
    return send_from_directory(preview_dir, filename)

@app.route('/previews/<slug>/')
def serve_preview_index(slug):
    """Sert l'index HTML du rapport local."""
    preview_dir = os.path.join(ROOT, 'reporter', 'reports', slug)
    return send_from_directory(preview_dir, 'index.html')

@app.route('/previews/<slug>')
def serve_preview_index_short(slug):
    """Redirect vers /previews/<slug>/"""
    return redirect(f'/previews/{slug}/')

@app.route('/api/previews')
def api_list_previews():
    """Liste tous les rapports locaux et leur statut."""
    reports_dir = os.path.join(ROOT, 'reporter', 'reports')
    previews = []
    
    # Check if directory exists
    if not os.path.exists(reports_dir):
        return jsonify({'previews': previews, 'warning': 'reports_dir not found'})
    
    try:
        for slug in os.listdir(reports_dir):
            slug_dir = os.path.join(reports_dir, slug)
            if os.path.isdir(slug_dir):
                index_path = os.path.join(slug_dir, 'index.html')
                has_local = os.path.exists(index_path)

                # Check if published (URL starts with https://)
                from database.db_manager import get_conn
                with get_conn() as conn:
                    row = conn.execute(
                        "SELECT lien_rapport FROM leads_audites WHERE lien_rapport LIKE ?",
                        (f"%{slug}%",)
                    ).fetchone()
                    is_published = row and row[0] and row[0].startswith('https://')

                previews.append({
                    'slug': slug,
                    'local': has_local,
                    'published': is_published,
                    'preview_url': f'/previews/{slug}/'
                })
    except Exception as e:
        logger.error(f"Erreur liste previews: {e}")
    
    return jsonify({'previews': previews})

@app.route('/api/previews/push', methods=['POST'])
def api_push_previews():
    """Push les rapports sélectionnés sur GitHub."""
    data = request.get_json() or {}
    slugs = data.get('slugs', [])
    
    if not slugs:
        return jsonify({'error': 'Aucun slug fourni'}), 400
    
    results = []
    reports_dir = os.path.join(ROOT, 'reporter', 'reports')
    
    from synthetiseur.github_publisher import _commit_files, AUDIT_DOMAIN
    from database.db_manager import get_conn
    
    for slug in slugs:
        slug_dir = os.path.join(reports_dir, slug)
        index_path = os.path.join(slug_dir, 'index.html')
        
        if not os.path.exists(index_path):
            results.append({'slug': slug, 'status': 'error', 'message': 'Fichier local introuvable'})
            continue
        
        try:
            # Read HTML and prepare files
            with open(index_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            files_to_commit = [{
                'path': f'{slug}/index.html',
                'content': html_content,
                'is_binary': False
            }]
            
            # Add images
            for fname in os.listdir(slug_dir):
                if fname.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                    fpath = os.path.join(slug_dir, fname)
                    with open(fpath, 'rb') as f:
                        files_to_commit.append({
                            'path': f'{slug}/{fname}',
                            'content': f.read(),
                            'is_binary': True
                        })
            
            # Commit to GitHub
            success = _commit_files(files_to_commit, f'Rapport {slug}')
            
            if success:
                public_url = f'https://{AUDIT_DOMAIN}/{slug}/'

                # Mettre à jour leads_audites ET emails_envoyes
                with get_conn() as conn:
                    conn.execute(
                        "UPDATE leads_audites SET lien_rapport = ? WHERE lien_rapport LIKE ?",
                        (public_url, f'%{slug}%')
                    )
                    # Aussi synchroniser le lien dans emails_envoyes
                    conn.execute(
                        "UPDATE emails_envoyes SET lien_rapport = ? WHERE lien_rapport LIKE ?",
                        (public_url, f'%{slug}%')
                    )
                    conn.commit()

                # Supprimer les fichiers locaux
                import shutil
                shutil.rmtree(slug_dir)

                results.append({'slug': slug, 'status': 'published', 'url': public_url})
            else:
                results.append({'slug': slug, 'status': 'error', 'message': 'Commit failed'})

        except Exception as e:
            logger.error(f"Erreur push {slug}: {e}")
            results.append({'slug': slug, 'status': 'error', 'message': str(e)})
    
    return jsonify({'results': results})


# ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ


# âââââââââââââââââââââââââââââââââââââââââââââââ
# GET /api/stats  â SQLite
# âââââââââââââââââââââââââââââââââââââââââââââââ

@app.route('/api/stats')
def api_stats():
    """
    Retourne les métriques globales du pipeline depuis SQLite.
    Supporte ?campaign_id=...
    """
    try:
        camp_id = request.args.get('campaign_id')
        campaign_ids = request.args.get('campaign_ids')
            
        stats = get_dashboard_stats(
            campaign_id=camp_id if camp_id and camp_id.isdigit() else None,
            date_start=request.args.get('date_start') or None,
            date_end=request.args.get('date_end') or None,
            campaign_ids=campaign_ids
        )

        # Adapter le format pour la compatibilité avec le frontend existant
        return jsonify({
            'pipeline': {
                'leads_scrapes':     stats.get('leads_scrapes', 0),
                'leads_audites':     stats.get('leads_audites', 0),
                'emails_prets':      stats.get('emails_prets', 0),
                'envoyes':           stats.get('envoyes', 0),
            },
            'performance': {
                'score_moyen':       stats.get('score_moyen', 0),
                'leads_prioritaires': stats.get('leads_prioritaires', 0),
                'pdfs_generes':      stats.get('pdfs_generes', 0),
            },
            'email_stats': {
                'nb_envoyes':        stats.get('envoyes', 0),
                'taux_ouverture':    stats.get('taux_ouverture', 0),
                'taux_clic':         stats.get('taux_clic', 0),
                'taux_reponse':      stats.get('taux_reponse', 0),
                'taux_rdv':          stats.get('taux_rdv', 0),
                'indice_perf':       stats.get('indice_perf', 0),
                'reponses_positives': stats.get('reponses_positives', 0),
                'rdv_obtenus':       stats.get('rdv_obtenus', 0),
            },
            'quotas': stats.get('quotas', {}),
            # Champs directs (compatibilitÃ© ancienne API)
            'leads_scrapes':     stats.get('leads_scrapes', 0),
            'leads_audites':     stats.get('leads_audites', 0),
            'audites':           stats.get('leads_audites', 0),
            'emails_prets':      stats.get('emails_prets', 0),
            'envoyes':           stats.get('envoyes', 0),
            'score_moyen':       stats.get('score_moyen', 0),
            'leads_prioritaires': stats.get('leads_prioritaires', 0),
            'rapports_html':      stats.get('pdfs_generes', 0),
            'nb_envoyes':        stats.get('envoyes', 0),
            'taux_ouverture':    stats.get('taux_ouverture'),
            'taux_reponse':      stats.get('taux_reponse'),
            'leads_site':        stats.get('leads_site', 0),
            'emails_trouves':    stats.get('emails_trouves', 0),
            'resend_configured': bool(os.getenv('RESEND_API_KEY')),
            'groq_configured':   bool(os.getenv('GROQ_API_KEY')),
        })
    except Exception as e:
        logger.error(f"GET /api/stats → {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/campaigns')
def api_campaigns():
    """
    Retourne la liste des campagnes.
    Paramètres: date_start, date_end (YYYY-MM-DD)
    """
    try:
        date_start = request.args.get('date_start')
        date_end = request.args.get('date_end')
        campaigns = get_all_campaigns(date_start, date_end)
        return jsonify({'campaigns': campaigns, 'total': len(campaigns)})
    except Exception as e:
        logger.error(f"GET /api/campaigns → {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/campaigns/<int:campaign_id>')
def api_campaign(campaign_id):
    """Retourne les stats d'une campagne par ID."""
    try:
        campaign = get_campaign_by_id(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campagne non trouvée'}), 404
        return jsonify(campaign)
    except Exception as e:
        logger.error(f"GET /api/campaigns/{campaign_id} → {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/campaigns/<int:campaign_id>', methods=['DELETE'])
def api_delete_campaign(campaign_id):
    """Supprime une campagne."""
    try:
        delete_campaign(campaign_id)
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"DELETE /api/campaigns/{campaign_id} → {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/collectes')
def api_collectes():
    """
    Retourne la liste des collectes (campagnes) avec stats.
    """
    try:
        collectes = get_all_campaigns()
        return jsonify({'collectes': collectes, 'total': len(collectes)})
    except Exception as e:
        logger.error(f"GET /api/collectes → {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/collectes/leads')
def api_collectes_leads():
    """
    Retourne les leads pour une ou plusieurs collectes.
    Param: collectes (CSV d'IDs, ex: 1,2,3) — si vide, retourne tous.
    """
    try:
        ids_str = request.args.get('collectes', '')
        limit = _safe_int(request.args.get('limit', 200))
        if limit > 500: limit = 500

        collectes_leads = get_leads_for_dashboard(campaign_ids=ids_str, limit=limit)
        return jsonify({'leads': collectes_leads, 'total': len(collectes_leads)})
    except Exception as e:
        logger.error(f"GET /api/collectes/leads → {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/collectes/stats')
def api_collectes_stats():
    """
    Retourne les stats agrégées pour une ou plusieurs collectes.
    Param: collectes (CSV d'IDs)
    """
    try:
        ids_str = request.args.get('collectes', '')
        if ids_str:
            ids = [int(x.strip()) for x in ids_str.split(',') if x.strip().isdigit()]
            where_clause = f"AND lb.campaign_id IN ({','.join('?' * len(ids))})" if ids else ""
            params = ids
            where_email = f"JOIN leads_bruts lb ON emails_envoyes.lead_id = lb.id AND lb.campaign_id IN ({','.join('?' * len(ids))})" if ids else ""
        else:
            where_clause = ""
            where_email = ""
            params = []

        with get_conn() as conn:
            row = conn.execute(f"""
                SELECT
                    COALESCE((SELECT COUNT(*) FROM leads_bruts lb WHERE 1=1 {where_clause}), 0) as leads_total,
                    COALESCE((SELECT COUNT(*) FROM leads_bruts lb WHERE site_web IS NOT NULL AND site_web != '' {where_clause}), 0) as leads_with_site,
                    COALESCE((SELECT COUNT(*) FROM leads_bruts lb WHERE email IS NOT NULL AND email != '' {where_clause}), 0) as leads_with_email,
                    COALESCE((SELECT COUNT(*) FROM leads_bruts lb WHERE (site_web IS NULL OR site_web = '') {where_clause}), 0) as leads_without_email,
                    COALESCE((SELECT COUNT(*) FROM leads_bruts lb WHERE statut IN ('audite','email_genere','envoye') {where_clause}), 0) as leads_audites
                FROM (SELECT 1) t
            """, params * 5 if ids else []).fetchone()

        return jsonify({
            'leads_total': row[0],
            'leads_with_site': row[1],
            'leads_with_email': row[2],
            'leads_without_email': row[3],
            'leads_audites': row[4],
        })
    except Exception as e:
        logger.error(f"GET /api/collectes/stats → {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/config', methods=['GET'])
def api_get_config():
    """Retourne la configuration actuelle (clés masquées)."""
    print("  [DEBUG] api_get_config called")
    try:
        from config_manager import get_config
        cfg = get_config()
        print(f"  [DEBUG] cfg keys: {list(cfg.keys())}")
        # Masquer les clés pour la sécurité
        def mask(s):
            s = str(s or '')
            return s[:4] + '****' + s[-4:] if len(s) > 8 else '****'
        
        # Détecter le provider d'envoi configuré
        resend_key = cfg.get('resend_key') or os.getenv('RESEND_API_KEY')
        brevo_key = cfg.get('brevo_key') or os.getenv('BREVO_API_KEY')
        
        if resend_key:
            email_provider = 'resend'
            provider_name = 'Resend'
            resend_configured = True
        elif brevo_key:
            email_provider = 'brevo'
            provider_name = 'Brevo'
            resend_configured = False
        else:
            email_provider = 'none'
            provider_name = 'Aucun'
            resend_configured = False
        
        return jsonify({
            'hunter_key': mask(cfg.get('hunter_api_key') or cfg.get('hunter_key')),
            'groq_key':   mask(cfg.get('groq_key') or os.getenv('GROQ_API_KEY')),
            'brevo_key':  mask(cfg.get('brevo_key') or os.getenv('BREVO_API_KEY')),
            'resend_key': mask(resend_key) if resend_key else None,
            'sheet_id':   os.getenv('GOOGLE_SHEETS_ID', 'Non configuré'),
            'email_provider': email_provider,
            'provider_name': provider_name,
            'resend_configured': resend_configured,
            'brevo_configured': bool(brevo_key),
            'groq_configured': bool(cfg.get('groq_key') or os.getenv('GROQ_API_KEY'))
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/config', methods=['POST'])
def api_save_config():
    """
    Sauvegarde les paramètres dans le fichier .env.
    """
    try:
        data = request.get_json() or {}
        env_updates = {}
        if data.get('brevo_key'): env_updates['BREVO_API_KEY'] = data['brevo_key']
        if data.get('groq_key'): env_updates['GROQ_API_KEY'] = data['groq_key']
        if data.get('hunter_key'): env_updates['HUNTER_API_KEY'] = data['hunter_key']
        if data.get('sheet_id'): env_updates['GOOGLE_SHEETS_ID'] = data['sheet_id']
        if data.get('resend_key'): env_updates['RESEND_API_KEY'] = data['resend_key']

        if env_updates:
            env_lines = []
            updated_keys = set()
            if os.path.exists(env_path):
                with open(env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        key = line.split('=')[0].strip()
                        if key in env_updates:
                            env_lines.append(f'{key}="{env_updates[key]}"\n')
                            updated_keys.add(key)
                        else:
                            env_lines.append(line)
            for key, val in env_updates.items():
                if key not in updated_keys:
                    env_lines.append(f'{key}="{val}"\n')
            with open(env_path, 'w', encoding='utf-8') as f:
                f.writelines(env_lines)
            # Recharger les variables dans le process actuel
            for key, val in env_updates.items():
                os.environ[key] = val

        return jsonify({'success': True, 'message': f'{len(env_updates)} clé(s) sauvegardée(s) dans .env'})
    except Exception as e:
        logger.error(f"POST /api/config → {e}")
        return jsonify({'error': str(e)}), 500



@app.route('/api/tracking')
def api_tracking():
    """
    Retourne les 10 derniers événements de tracking pour le flux live du dashboard.
    """
    try:
        date_start = request.args.get('date_start') or None
        date_end = request.args.get('date_end') or None
        
        from database.db_manager import get_conn
        with get_conn() as conn:
            query = """
                SELECT 
                    COALESCE(lb.nom, 'Test') as nom, 
                    ee.ouvert, ee.clique, ee.bounce, ee.spam,
                    ee.date_ouverture, ee.date_clic, ee.date_envoi
                FROM emails_envoyes ee
                LEFT JOIN leads_bruts lb ON lb.id = ee.lead_id
            """
            params = []
            if date_start and date_end:
                query += " WHERE ee.date_envoi >= ? AND ee.date_envoi <= ? "
                params.extend([date_start + ' 00:00:00', date_end + ' 23:59:59'])
            
            query += " ORDER BY ee.date_envoi DESC LIMIT 15 "
            
            rows = conn.execute(query, params).fetchall()
            return jsonify({'events': [dict(r) for r in rows]})
    except Exception as e:
        logger.error(f"GET /api/tracking → {e}")
        return jsonify({'error': str(e)}), 500


# ââââââââââââââââââââââââââââââââââââââââââââââââ
# GET /api/leads  â SQLite
# ââââââââââââââââââââââââââââââââââââââââââââââââââ

@app.route('/api/leads')
def api_leads():
    """
    Retourne la liste des leads depuis SQLite.
    ParamÃ¨tres: 
    - statut: tous|audite|en_attente|envoye
    - site: tous|avec|sans
    - email: tous|avec|sans
    - note: tous|high|low (high=â¥4â, low=<4â)
    - page: numÃ©ro de page (dÃ©faut 1)
    - limit: nombre par page (dÃ©faut 50)
    """
    try:
        # ParamÃ¨tres de filtrage
        statut = request.args.get('statut', 'tous')
        site_filter = request.args.get('site', 'tous')
        email_filter = request.args.get('email', 'tous')
        note_filter = request.args.get('note', 'tous')
        
        # Paramètres de pagination
        page = _safe_int(request.args.get('page', 1))
        limit = _safe_int(request.args.get('limit', 50))
        camp_id = request.args.get('campaign_id')
        if camp_id and camp_id.isdigit():
            camp_id = int(camp_id)
        else:
            camp_id = None
        date_start = request.args.get('date_start') or None
        date_end = request.args.get('date_end') or None

        if limit > 100: limit = 100
        if page < 1: page = 1
        
        rows = get_leads_for_dashboard(camp_id, date_start, date_end, request.args.get('campaign_ids'))

        # Filtrage par statut
        if statut == 'audite':
            rows = [r for r in rows if r.get('statut') in ('audite', 'email_genere', 'envoye')]
        elif statut == 'en_attente':
            rows = [r for r in rows if r.get('statut') == 'en_attente']
        elif statut == 'envoye':
            rows = [r for r in rows if r.get('statut') == 'envoye']
        elif statut == 'non_envoye':
            rows = [r for r in rows if r.get('statut') not in ('envoye', 'repondu')]

        # Filtrage par site web
        if site_filter == 'avec':
            rows = [r for r in rows if r.get('site_web')]
        elif site_filter == 'sans':
            rows = [r for r in rows if not r.get('site_web')]

        # Filtrage par email
        if email_filter == 'avec':
            rows = [r for r in rows if r.get('email')]
        elif email_filter == 'sans':
            rows = [r for r in rows if not r.get('email')]

        # Filtrage par note Google
        if note_filter == 'high':
            rows = [r for r in rows if _safe_float(r.get('note', 0)) >= 4]
        elif note_filter == 'low':
            rows = [r for r in rows if _safe_float(r.get('note', 0)) < 4]

        total = len(rows)
        total_pages = (total + limit - 1) // limit if total > 0 else 1
        
        # Pagination
        start = (page - 1) * limit
        end = start + limit
        paged_rows = rows[start:end]

        # Normalisation pour la compatibilitÃ© frontend
        leads = []
        for r in paged_rows:
            lead_site = r.get('site_web', '')
            leads.append({
                'id':           r.get('id'),
                'nom':          r.get('nom', ''),
                'ville':        r.get('ville', ''),
                'secteur':      r.get('secteur', r.get('category', '')),
                'note':         _safe_float(r.get('note', r.get('rating', 0))),
                'avis':         _safe_int(r.get('avis', r.get('nb_avis', 0))),
                'site_web':     lead_site,
                'email':        r.get('email', ''),
                'telephone':    r.get('telephone', ''),
                'statut':       r.get('statut', 'en_attente'),
                'a_site':       bool(lead_site),
                'a_email':      bool(r.get('email')),
                'score_perf':   _safe_int(r.get('score_perf', r.get('mobile_score', 0))),
                'score_seo':    _safe_int(r.get('score_seo', 0)),
                'score_urgence': _safe_float(r.get('score_urgence', 0)),
                'lcp':          r.get('lcp', r.get('lcp_ms', '')),
                'lien_rapport': r.get('lien_rapport', ''),
                'email_corps':  r.get('email_corps', ''),
                'email_objet':  r.get('email_objet', ''),
                'approuve':     bool(r.get('approuve', False)),
                'profile':      r.get('profile', ''),
            })

        return jsonify({
            'leads': leads, 
            'total': total,
            'page': page,
            'limit': limit,
            'total_pages': total_pages
        })

    except Exception as e:
        logger.error(f"GET /api/leads â {e}")
        return jsonify({'error': str(e)}), 500


# âââââââââââââââââââââââââââââââââââââââââââââââ
# UPDATE & DELETE LEADS  â SQLite
# âââââââââââââââââââââââââââââââââââââââââââââââ

@app.route('/api/leads/<int:lead_id>')
def api_lead(lead_id):
    """Retourne le profil complet + score d'un seul lead."""
    try:
        from database.db_manager import get_conn
        with get_conn() as conn:
            # Get lead from leads_bruts
            lead = conn.execute("SELECT * FROM leads_bruts WHERE id = ?", (lead_id,)).fetchone()
            if not lead:
                return jsonify({'error': 'Lead non trouvé'}), 404
            
            lead_data = dict(lead)
            
            # Get audit from leads_audites
            audit = conn.execute("SELECT * FROM leads_audites WHERE lead_id = ?", (lead_id,)).fetchone()
            audit_data = dict(audit) if audit else {}
            
            # Combine lead + audit data
            return jsonify({
                'id': lead_data.get('id'),
                'nom': lead_data.get('nom', ''),
                'ville': lead_data.get('ville', ''),
                'secteur': lead_data.get('category', lead_data.get('secteur', '')),
                'note': _safe_float(lead_data.get('rating', 0)),
                'avis': _safe_int(lead_data.get('nb_avis', 0)),
                'site_web': lead_data.get('site_web', ''),
                'email': lead_data.get('email', ''),
                'telephone': lead_data.get('telephone', ''),
                'statut': lead_data.get('statut', 'en_attente'),
                'score_perf': _safe_int(audit_data.get('mobile_score', 0)),
                'score_seo': _safe_int(audit_data.get('score_seo', 0)),
                'score_urgence': _safe_float(audit_data.get('score_urgence', 0)),
                'lcp': audit_data.get('lcp_ms', ''),
                'lien_rapport': audit_data.get('lien_rapport', ''),
                'email_corps': audit_data.get('email_corps', ''),
                'email_objet': audit_data.get('email_objet', ''),
                'approuve': bool(audit_data.get('approuve', False)),
                'profile': audit_data.get('profile', ''),
            })
    except Exception as e:
        logger.error(f"GET /api/leads/{lead_id} → {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/leads/<int:lead_id>', methods=['PUT'])
def api_update_lead(lead_id):
    """Met à jour les informations d'un lead (nom, ville, site, email, adresse, tel)."""
    try:
        data = request.get_json() or {}
        update_lead(lead_id, data)
        return jsonify({'success': True, 'lead_id': lead_id})
    except Exception as e:
        logger.error(f"PUT /api/leads/{lead_id} → {e}")
        return jsonify({'error': str(e)}), 500
    """Met Ã  jour les informations d'un lead (nom, ville, site, email, adresse, tel)."""
    try:
        data = request.get_json() or {}
        update_lead(lead_id, data)
        return jsonify({'success': True, 'lead_id': lead_id})
    except Exception as e:
        logger.error(f"PUT /api/leads/{lead_id} â {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/leads/<int:lead_id>', methods=['DELETE'])
def api_delete_lead(lead_id):
    """Supprime un lead et toutes ses donnÃ©es en cascade."""
    try:
        delete_lead(lead_id)
        return jsonify({'success': True, 'lead_id': lead_id})
    except Exception as e:
        logger.error(f"DELETE /api/leads/{lead_id} â {e}")
        return jsonify({'error': str(e)}), 500


# ââââââââââââââââââââââââââââââââââââââââââââââââ
# GET /api/emails  â SQLite
# ââââââââââââââââââââââââââââââââââââââââââââââââ

@app.route('/api/emails')
def api_emails():
    """
    Retourne les emails générés depuis SQLite.
    Supporte ?campaign_id=...
    """
    try:
        camp_id = request.args.get('campaign_id')
        if camp_id and camp_id.isdigit():
            camp_id = int(camp_id)
        else:
            camp_id = None
        date_start = request.args.get('date_start') or None
        date_end = request.args.get('date_end') or None

        emails  = get_emails_for_dashboard(camp_id, date_start, date_end)
        # Tous les emails depuis emails_envoyes pour la section "envoyés"
        envoyes = []
        for r in get_crm_data(date_start=date_start, date_end=date_end):
            envoyes.append({
                'nom':        r.get('nom', ''),
                'email':      r.get('prospect_email', ''),
                'email_objet': r.get('email_objet', ''),
                'date_envoi': r.get('date_envoi', ''),
                'ouvert':     bool(r.get('ouvert', False)),
                'repondu':    bool(r.get('repondu', False)),
            })

        # Normalisation des emails gÃ©nÃ©rÃ©s
        emails_formatted = []
        for r in emails:
            emails_formatted.append({
                'nom':          r.get('nom', ''),
                'email':        r.get('email', ''),
                'objet':        r.get('objet', r.get('email_objet', '')),
                'corps':        r.get('corps', r.get('email_corps', '')),
                'score_urgence': _safe_float(r.get('score_urgence', 0)),
                'approuve':     bool(r.get('approuve', False)),
                'lien_rapport': r.get('lien_rapport', ''),
                'statut':       'pret',
            })

        return jsonify({
            'emails':     emails_formatted,
            'envoyes':    envoyes,
            'total':      len(emails_formatted),
            'nb_envoyes': len(envoyes)
        })

    except Exception as e:
        logger.error(f"GET /api/emails â {e}")
        return jsonify({'error': str(e)}), 500


# ââââââââââââââââââââââââââââââââââââââââââââââââ
# GET /api/rapports  â SQLite
# ââââââââââââââââââââââââââââââââââââââââââââââââ

@app.route('/api/rapports')
def api_rapports():
    """
    Retourne la liste des rapports PDF gÃ©nÃ©rÃ©s depuis SQLite.
    """
    try:
        date_start = request.args.get('date_start') or None
        date_end = request.args.get('date_end') or None
        rows = get_audits_with_reports(date_start, date_end)
        rapports = []
        for r in rows:
            rapports.append({
                'nom':          r.get('nom', ''),
                'ville':        r.get('ville', ''),
                'secteur':      r.get('category', ''),
                'score':        _safe_float(r.get('score_urgence', 0)),
                'lien_rapport': r.get('lien_rapport', ''),
                'lien_pdf':     r.get('lien_pdf', r.get('lien_rapport', '')),
                'date_audit':   r.get('date_audit', ''),
            })
        return jsonify({'rapports': rapports, 'total': len(rapports)})

    except Exception as e:
        logger.error(f"GET /api/rapports â {e}")
        return jsonify({'error': str(e)}), 500


# ââââââââââââââââââââââââââââââââââââââââââââââââ
# GET /api/crm  â SQLite
# ââââââââââââââââââââââââââââââââââââââââââââââââ

@app.route('/api/crm')
def api_crm():
    """
    Retourne les donnÃ©es CRM (suivi commercial) depuis SQLite.
    Supporte ?filter=ouverts|cliques|repondus|positifs|rdv|bounces
    """
    try:
        f = request.args.get('filter', 'tous')
        date_start = request.args.get('date_start') or None
        date_end = request.args.get('date_end') or None
        rows = get_crm_data(f, date_start, date_end)
        return jsonify({'crm': rows, 'total': len(rows)})

    except Exception as e:
        logger.error(f"GET /api/crm â {e}")
        return jsonify({'error': str(e)}), 500


# ââââââââââââââââââââââââââââââââââââââââââââââââââ
# POST /api/crm/update  â SQLite
# âââââââââââââââââââââââââââââââââââââââââââââââââââââ

@app.route('/api/crm/update', methods=['POST'])
def api_crm_update():
    """
    Mise Ã  jour manuelle des donnÃ©es CRM depuis le dashboard.
    Body JSON : {email_id, type_reponse, rdv_confirme, notes, ...}
    """
    try:
        data = request.get_json() or {}
        email_id = data.pop('email_id', None)
        if not email_id:
            return jsonify({'error': 'email_id requis'}), 400
        update_crm_manual(int(email_id), data)
        return jsonify({'success': True})

    except Exception as e:
        logger.error(f"POST /api/crm/update â {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/emails/<int:email_id>')
def api_email_details(email_id):
    """
    Retourne les dÃ©tails complets d'un email envoyÃ© (objet, corps, etc.).
    """
    try:
        from database.db_manager import get_conn
        with get_conn() as conn:
            row = conn.execute("""
                SELECT 
                    ee.*, 
                    lb.nom as prospect_nom,
                    lb.email as prospect_email
                FROM emails_envoyes ee
                LEFT JOIN leads_bruts lb ON lb.id = ee.lead_id
                WHERE ee.id = ?
            """, (email_id,)).fetchone()
            
            if not row:
                return jsonify({'error': 'Email introuvable'}), 404

            return jsonify(dict(row))
    except Exception as e:
        logger.error(f"GET /api/emails/{email_id} â {e}")
        return jsonify({'error': str(e)}), 500


# ââââââââââââââââââââââââââââââââââââââââââââââââ
# POST /api/webhook/resend_legacy (Brevo) â Tracking emails
# âââââââââââââââââââââââââââââââââââââââââââââââââââ

@app.route('/api/webhook/brevo', methods=['POST'])
def api_webhook_brevo():
    try:
        data = request.get_json() or {}
        event_type = data.get('event')
        message_id = data.get('message-id')
        if not message_id or not event_type:
            return jsonify({'ok': True}), 200
        
        update_map = {
            'opened':     {'ouvert': 1, 'date_ouverture': datetime.now().isoformat()},
            'clicks':     {'clique': 1, 'date_clic': datetime.now().isoformat()},
            'delivered':  {'statut_envoi': 'delivré'},
            'deferred':   {'statut_envoi': 'différé'},
            'soft_bounce': {'bounce': 1, 'statut_envoi': 'soft_bounce'},
            'hard_bounce': {'bounce': 1, 'statut_envoi': 'hard_bounce'},
            'spam':        {'spam': 1, 'statut_envoi': 'spam'}
        }
        if event_type in update_map:
            from database.db_manager import get_conn
            with get_conn() as conn:
                # Chercher soit dans message_id_resend (Resend) soit message_id_brevo (Brevo)
                conn.execute("""
                    UPDATE emails_envoyes 
                    SET ouvert = COALESCE(?, ouvert), 
                        date_ouverture = COALESCE(?, date_ouverture),
                        clique = COALESCE(?, clique),
                        date_clic = COALESCE(?, date_clic),
                        statut_envoi = COALESCE(?, statut_envoi),
                        bounce = COALESCE(?, bounce),
                        spam = COALESCE(?, spam)
                    WHERE message_id_resend = ? OR message_id_brevo = ?
                """, (
                    update_map[event_type].get('ouvert'),
                    update_map[event_type].get('date_ouverture'),
                    update_map[event_type].get('clique'),
                    update_map[event_type].get('date_clic'),
                    update_map[event_type].get('statut_envoi'),
                    update_map[event_type].get('bounce'),
                    update_map[event_type].get('spam'),
                    message_id, message_id
                ))
            if event_type == 'opened':
                threading.Thread(target=_alert_opening, args=(message_id, 'brevo'), daemon=True).start()
        return jsonify({'ok': True}), 200
    except Exception as e:
        return jsonify({'ok': True}), 200

@app.route('/webhooks/resend', methods=['POST'])
def api_webhook_resend():
    try:
        data = request.get_json() or {}
        event_type = data.get('type')
        msg_data = data.get('data', {})
        message_id = msg_data.get('id') or msg_data.get('email_id')
        
        # Log V17 pour voir ce que Resend nous envoie réellement
        logger.error(f"[V17 WEBHOOK RESEND] Payload: {json.dumps(data)}")
        
        if not message_id or not event_type:
            return jsonify({'ok': True}), 200
        
        update_map = {
            'email.opened': {'ouvert': 1, 'date_ouverture': datetime.now().isoformat()},
            'email.clicked': {'clique': 1, 'date_clic': datetime.now().isoformat()},
            'email.delivered': {'statut_envoi': 'delivré'}
        }
        if event_type in update_map:
            from database.db_manager import update_email_tracking
            update_email_tracking(message_id, update_map[event_type])
            if event_type == 'email.opened':
                threading.Thread(target=_alert_opening, args=(message_id, 'resend'), daemon=True).start()
        return jsonify({'ok': True}), 200
    except Exception as e:
        logger.error(f"Webhook Resend error: {e}")
        return jsonify({'ok': True}), 200

def _alert_opening(message_id, provider='resend'):
    try:
        from envoi.brevo_sender import send_email
        from database.db_manager import get_conn
        id_col = 'message_id_resend' if provider == 'resend' else 'message_id_brevo'
        with get_conn() as conn:
            prospect = conn.execute(f'SELECT lb.nom FROM leads_bruts lb JOIN emails_envoyes ee ON ee.lead_id = lb.id WHERE ee.{id_col} = ?', (message_id,)).fetchone()
            nome = prospect['nom'] if prospect else 'un prospect'
        subject = f"🔔 Ouvert ({provider}) : {nome} vient d'ouvrir ton mail"
        content = f"<p>Bonne nouvelle ! <strong>{nome}</strong> a ouvert l'audit ({provider}) à {datetime.now().strftime('%H:%M')}.</p>"
        send_email('jmedansi@incidenx.com', subject, content)
    except Exception as e:
        pass

# POST /api/scraper/launch
# â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�â•�
_scraper_job = {'running': False, 'logs': [], 'returncode': None, 'campaign_id': None, 'total': 0, 'current': 0, 'emails_found': 0, 'sites_found': 0}

@app.route('/api/scraper/launch', methods=['POST'])
def api_scraper_launch():
    """
    Lance le scraper en arriÃ¨re-plan.
    Body JSON : {keyword, city, limit, min_emails}
    """
    try:
        data    = request.get_json() or {}
        keyword = data.get('keyword', '').strip()
        city    = data.get('city', '').strip()
        limit   = _safe_int(data.get('limit', 20))
        min_emails = data.get('min_emails')
        multi_zone = data.get('multi_zone', False)

        if not keyword or not city:
            return jsonify({'error': 'keyword et city sont requis'}), 400

        campaign_name = data.get('campaign_name', f"Campagne {datetime.now().strftime('%d/%m %H:%M')}")
        
        if _scraper_job['running']:
            return jsonify({'error': 'Un scraping est déjà en cours'}), 409

        # CrÃ©er la campagne en base
        try:
            camp_id = insert_campaign(campaign_name, keyword, city, nb_demande=limit)
            logger.error(f"[DASHBOARD] Campagne créée: {campaign_name} (ID: {camp_id})")
        except Exception as e:
            logger.error(f"Erreur création campagne: {e}")
            return jsonify({'error': f"Impossible de créer la campagne: {e}"}), 500

        cmd = [
            sys.executable,
            os.path.join(ROOT, 'scraper', 'main.py'),
            '--keyword',     keyword,
            '--city',        city,
            '--limit',       str(limit),
            '--campaign-id', str(camp_id)
        ]
        
        if min_emails:
            cmd.extend(['--min-emails', str(min_emails)])
        
        if multi_zone:
            cmd.append('--multi-zone')

        def _run():
            import re
            _scraper_job['running']     = True
            _scraper_job['logs']        = []
            _scraper_job['returncode']  = None
            _scraper_job['campaign_id'] = camp_id
            _scraper_job['total']      = limit
            _scraper_job['current']     = 0
            _scraper_job['emails_found'] = 0
            _scraper_job['sites_found']  = 0
            try:
                proc = subprocess.Popen(
                    cmd, cwd=ROOT,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding='utf-8', errors='replace'
                )
                for line in proc.stdout:
                    stripped = line.rstrip()
                    _scraper_job['logs'].append(stripped)
                    # Total attendu: "[OK] N fiches a extraire"
                    m_total = re.search(r'\[OK\]\s*(\d+)\s*fiches?\s*a?\s*extraire', stripped)
                    if m_total:
                        _scraper_job['total'] = int(m_total.group(1))
                    # Multi-passes: "Limite N > 120: mode multi-passes" → récupérer la limite totale
                    m_limit = re.search(r'Limite (\d+)', stripped)
                    if m_limit and 'multi-passes' in stripped:
                        _scraper_job['total'] = int(m_limit.group(1))
                    # Compteur global: "+N nouveaux leads (total: X)"
                    m_global = re.search(r'total:\s*(\d+)', stripped)
                    if m_global:
                        _scraper_job['current'] = int(m_global.group(1))
                    # Compter les emails trouvés (toutes méthodes)
                    if ('Email trouvé' in stripped or 'Email page web' in stripped
                            or 'Email site' in stripped):
                        _scraper_job['emails_found'] += 1
                    # Compter les téléphones trouvés sur site
                    if 'Telephone trouve' in stripped or 'Téléphone trouvé' in stripped:
                        _scraper_job['sites_found'] += 1
                    # Compter TOUTE fiche traitée dans une passe unique
                    if ('[REJETE]' in stripped
                            or stripped.startswith('   [OK]')
                            or stripped.startswith('   [--]')):
                        if not m_global:  # éviter le double-comptage avec multi-passes
                            _scraper_job['current'] += 1
                    # Fallback DB toutes les 5 lignes
                    if camp_id and len(_scraper_job['logs']) % 5 == 0:
                        try:
                            from database.db_manager import get_conn
                            with get_conn() as c:
                                cnt = c.execute(
                                    "SELECT COUNT(*) FROM leads_bruts WHERE campaign_id = ?",
                                    (camp_id,)
                                ).fetchone()
                                if cnt and cnt[0] > 0:
                                    _scraper_job['emails_found'] = cnt[0]
                        except:
                            pass
                proc.wait()
                _scraper_job['returncode'] = proc.returncode
            except Exception as e:
                _scraper_job['logs'].append(f'ERREUR: {e}')
                _scraper_job['returncode'] = -1
            finally:
                _scraper_job['running'] = False

        threading.Thread(target=_run, daemon=True).start()

        msg = f'Scraping lancÃ© : {keyword} Ã  {city} ({limit} leads)'
        if min_emails:
            msg += f', objectif {min_emails} emails minimum'
        
        return jsonify({
            'statut':  'lance',
            'campaign_id': camp_id,
            'cmd':     ' '.join(cmd),
            'message': msg
        })

    except Exception as e:
        logger.error(f"POST /api/scraper/launch â {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/scraper/status')
def api_scraper_status():
    """Retourne le statut et les logs du scraping en cours avec stats live."""
    camp_id = _scraper_job.get('campaign_id')
    live = {}
    if camp_id and _scraper_job.get('running'):
        try:
            with get_conn() as conn:
                row = conn.execute("""
                    SELECT COUNT(*) FROM leads_bruts WHERE campaign_id = ?
                """, (camp_id,)).fetchone()
                live['scraped'] = row[0] if row else 0
                row2 = conn.execute("""
                    SELECT COUNT(*) FROM leads_bruts WHERE campaign_id = ? AND site_web IS NOT NULL AND site_web != ''
                """, (camp_id,)).fetchone()
                live['with_site'] = row2[0] if row2 else 0
                row3 = conn.execute("""
                    SELECT COUNT(*) FROM leads_bruts WHERE campaign_id = ? AND email IS NOT NULL AND email != ''
                """, (camp_id,)).fetchone()
                live['with_email'] = row3[0] if row3 else 0
        except Exception as e:
            logger.warning(f"Live stats error: {e}")
    
    return jsonify({
        'running':    _scraper_job['running'],
        'logs':       _scraper_job['logs'][-50:],
        'returncode': _scraper_job['returncode'],
        'campaign_id': camp_id,
        'total':      _scraper_job.get('total', 0),
        'current':    live.get('scraped', _scraper_job.get('current', 0)),
        'with_site':  live.get('with_site', _scraper_job.get('sites_found', 0)),
        'with_email': live.get('with_email', _scraper_job.get('emails_found', 0)),
    })


# âââââââââââââââââââââââââââââââââââââââââââââââ
# POST /api/audit/cleanup
@app.route('/api/audit/cleanup', methods=['POST'])
def api_audit_cleanup():
    """
    Supprime le dossier local et reset lien_rapport pour relancer proprement.
    Body JSON : {lead_id: int}
    """
    try:
        data = request.get_json() or {}
        lead_id = data.get('lead_id')
        
        if not lead_id:
            return jsonify({'error': 'lead_id requis'}), 400
        
        # Récupérer le nom du lead
        from database.db_manager import get_lead_by_id, get_conn
        lead = get_lead_by_id(lead_id)
        
        if not lead:
            return jsonify({'error': 'Lead non trouvé'}), 404
        
        lead_nom = lead.get('nom', '')
        
        # Supprimer le dossier local
        import shutil
        import re
        reports_dir = os.path.join(ROOT, 'reporter', 'reports')
        
        if lead_nom:
            # Générer le slug (identique à generate_slug() Python)
            slug = lead_nom.lower()
            slug = re.sub(r'\s+', '-', slug)
            slug = slug[:50]
            
            slug_dir = os.path.join(reports_dir, slug)
            if os.path.exists(slug_dir) and os.path.isdir(slug_dir):
                logger.info(f"Suppression du dossier de rapport local : {slug_dir}")
                shutil.rmtree(slug_dir)
        
        # Reset lien_rapport dans la base
        with get_conn() as conn:
            conn.execute(
                "UPDATE leads_audites SET lien_rapport = NULL WHERE lead_id = ?",
                (lead_id,)
            )
            conn.commit()
        
        logger.info(f"Cleanup terminé pour lead_id={lead_id}")
        return jsonify({'success': True, 'lead_id': lead_id})
        
    except Exception as e:
        logger.error(f"POST /api/audit/cleanup → {e}")
        return jsonify({'error': str(e)}), 500


# POST /api/audit/launch
# ââââââââââââââââââââââââââââââââââââââââââââââââ

_audit_job = {'running': False, 'logs': [], 'returncode': None, 'total': 0, 'current': 0, 'failed': 0}

@app.route('/api/audit/launch', methods=['POST'])
def api_audit_launch():
    """
    Lance l'auditeur sur les leads en attente (depuis SQLite).
    Body JSON : {limit: int}
    """
    try:
        data  = request.get_json() or {}
        limit = _safe_int(data.get('limit', 0)) or None
        lead_ids = data.get('lead_ids', []) # On peut passer une liste d'IDs
        lead_names = data.get('lead_names', []) # On peut passer une liste de noms
        logger.info(f"audit/launch: lead_ids={lead_ids}, lead_names={lead_names}, limit={limit}")

        if _audit_job['running']:
            return jsonify({'error': 'Un audit est déjà en cours'}), 409

        # Nettoyer les dossiers de rapports locaux existants pour les leads spécifiés
        # Cela garantit que chaque audit repart de zéro
        try:
            import shutil
            import re
            from database.db_manager import get_lead_by_id
            reports_dir = os.path.join(ROOT, 'reporter', 'reports')
            # S'assurer que le répertoire de base existe
            os.makedirs(reports_dir, exist_ok=True)
            
            # Collect all lead names to clean
            lead_noms_to_clean = []
            
            if lead_names:
                lead_noms_to_clean.extend(lead_names)
            elif lead_ids:
                # Fetch lead names from IDs
                for lid in lead_ids:
                    lead = get_lead_by_id(lid)
                    if lead and lead.get('nom'):
                        lead_noms_to_clean.append(lead['nom'])
            
            for lead_nom in lead_noms_to_clean:
                # G\u00e9n\u00e9rer le slug align\u00e9 sur generate_slug() Python ET makeSlug() JS
                slug = re.sub(r'[^a-z0-9\s]', '', lead_nom.lower())
                slug = re.sub(r'\s+', '-', slug).strip('-')[:50]


                if slug:  # Éviter les slugs vides
                    slug_dir = os.path.join(reports_dir, slug)
                    if os.path.exists(slug_dir) and os.path.isdir(slug_dir):
                        logger.info(f"Suppression du dossier de rapport local existant : {slug_dir}")
                        shutil.rmtree(slug_dir)
                        logger.info(f"Dossier de rapport local supprimé avec succès : {slug_dir}")
        except Exception as e:
            logger.error(f"Erreur lors du nettoyage des dossiers de rapports locaux : {e}")
            # On continue quand même avec le lancement de l'audit

        cmd = [sys.executable, '-u', os.path.join(ROOT, 'auditeur', 'main.py')]

        # Pré-remplir total depuis le nombre de leads demandés
        if lead_names:
            _audit_job['total'] = len(lead_names)
            cmd.extend(['--leads'] + lead_names)
        elif lead_ids:
            _audit_job['total'] = len(lead_ids)
            cmd.extend(['--ids'] + [str(x) for x in lead_ids])
        elif limit:
            _audit_job['total'] = limit
            cmd.extend(['--limit', str(limit)])

        def _run():
            _audit_job['running']    = True
            _audit_job['logs']       = []
            _audit_job['returncode'] = None
            _audit_job['total']      = 0
            _audit_job['current']    = 0
            _audit_job['failed']     = 0
            try:
                proc = subprocess.Popen(
                    cmd, cwd=ROOT,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding='utf-8', errors='replace'
                )
                for line in proc.stdout:
                    line_s = line.rstrip()
                    _audit_job['logs'].append(line_s)
                    # Total depuis la ligne "N leads à auditer depuis SQLite"
                    if 'leads' in line_s and ('auditer' in line_s or 'à auditer' in line_s):
                        import re as _re
                        m = _re.search(r'(\d+) leads', line_s)
                        if m:
                            n = int(m.group(1))
                            if n > _audit_job['total']:
                                _audit_job['total'] = n
                    # Compteur de succès
                    if 'Audit enregistré' in line_s or '[SQLite] Audit enregistré' in line_s:
                        _audit_job['current'] += 1
                    # Compteur d'échecs
                    elif 'ÉCHOUÉ' in line_s or 'audit_echoue' in line_s:
                        _audit_job['failed'] += 1
                        _audit_job['current'] += 1  # compte quand même
                    elif 'Terminé' in line_s and 'Audit' in line_s:
                        # Ligne finale: [Terminé] Audit SQLite terminé pour N lead(s)
                        import re as _re
                        m = _re.search(r'(\d+) lead', line_s)
                        if m:
                            _audit_job['current'] = max(_audit_job['current'], int(m.group(1)))
                proc.wait()
                _audit_job['returncode'] = proc.returncode
            except Exception as e:
                _audit_job['logs'].append(f'ERREUR: {e}')
                _audit_job['returncode'] = -1
            finally:
                _audit_job['running'] = False

        threading.Thread(target=_run, daemon=True).start()

        return jsonify({
            'statut':  'lance',
            'message': f'Audit lancÃ© ({limit or "tous les leads en attente"})'
        })

    except Exception as e:
        logger.error(f"POST /api/audit/launch → {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings/identity', methods=['POST'])
def api_settings_identity():
    """
    Sauvegarde le nom, l'email et la signature de l'expéditeur dans le fichier .env.
    """
    try:
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        email = data.get('email', '').strip()
        signature = data.get('signature', '').strip()

        if not name or not email:
            return jsonify({'error': 'Nom et Email requis'}), 400

        # Mise à jour du fichier .env
        env_lines = []
        found_name = False
        found_email = False
        
        if os.path.exists(env_path):
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('BREVO_SENDER_NAME='):
                        env_lines.append(f'BREVO_SENDER_NAME="{name}"\n')
                        found_name = True
                    elif line.startswith('BREVO_SENDER_EMAIL='):
                        env_lines.append(f'BREVO_SENDER_EMAIL="{email}"\n')
                        found_email = True
                    else:
                        env_lines.append(line)
        
        if not found_name: env_lines.append(f'BREVO_SENDER_NAME="{name}"\n')
        if not found_email: env_lines.append(f'BREVO_SENDER_EMAIL="{email}"\n')

        with open(env_path, 'w', encoding='utf-8') as f:
            f.writelines(env_lines)

        # Rechargement des variables d'env pour le process actuel
        os.environ["BREVO_SENDER_NAME"] = name
        os.environ["BREVO_SENDER_EMAIL"] = email
        
        return jsonify({'success': True, 'message': 'Identité sauvegardée et .env mis à jour'})
    except Exception as e:
        logger.error(f"POST /api/settings/identity → {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/audit/status')
def api_audit_status():
    """Retourne le statut et les logs du dernier audit."""
    return jsonify({
        'running':    _audit_job['running'],
        'logs':       _audit_job['logs'],
        'returncode': _audit_job['returncode'],
        'total':      _audit_job.get('total', 0),
        'current':    _audit_job.get('current', 0),
        'failed':     _audit_job.get('failed', 0),
    })


# âââââââââââââââââââââââââââââââââââââââââââââââ
# POST /api/email/approve  â SQLite
# âââââââââââââââââââââââââââââââââââââââââââââââ

@app.route('/api/email/approve', methods=['POST'])
def api_email_approve():
    """
    Met Ã  jour le statut d'approbation d'un email dans SQLite.
    Body JSON : {lead_id: "Nom du lead", approved: true|false}
    """
    try:
        data     = request.get_json() or {}
        lead_nom = data.get('lead_id', '').strip()
        approved = bool(data.get('approved', False))

        if not lead_nom:
            return jsonify({'error': 'lead_id (nom) requis'}), 400

        update_audit_approval(lead_nom, approved)
        return jsonify({'statut': 'ok', 'lead_id': lead_nom, 'approuve': approved})

    except Exception as e:
        logger.error(f"POST /api/email/approve â {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/email/update', methods=['PUT'])
def api_email_update():
    """
    Met Ã  jour manuellement le sujet et le corps d'un email gÃ©nÃ©rÃ©.
    Body JSON : {lead_id: "Nom du lead", email_objet: "...", email_corps: "..."}
    """
    try:
        data     = request.get_json() or {}
        lead_nom = data.get('lead_id', '').strip()
        objet    = data.get('email_objet', '').strip()
        corps    = data.get('email_corps', '').strip()

        if not lead_nom:
            return jsonify({'error': 'lead_id (nom) requis'}), 400

        update_audit_email_content(lead_nom, objet, corps)
        return jsonify({'statut': 'ok', 'lead_id': lead_nom})

    except Exception as e:
        logger.error(f"PUT /api/email/update â {e}")
        return jsonify({'error': str(e)}), 500


# âââââââââââââââââââââââââââââââââââââââââââââââ
# POST /api/email/generate  â GÃ©nÃ¨re les emails via copywriter
# âââââââââââââââââââââââââââââââââââââââââââââââ

@app.route('/api/email/generate', methods=['POST'])
def api_email_generate():
    """
    GÃ©nÃ¨re les emails pour les leads auditÃ©s sans email_corps.
    Utilise le copywriter pour crÃ©er le contenu.
    """
    try:
        data = request.get_json() or {}
        lead_nom = data.get('lead_nom', '').strip()
        
        logger.error(f"[EMAIL GENERATE] Debut generation pour lead_nom={lead_nom}")
        
        with get_conn() as conn:
            # ALWAYS regenerate leads without email_objet (regardless of lead_nom)
            # This ensures copywriter is used every time
            logger.error(f"[EMAIL GENERATE] Regenerating all leads without email_objet")
            # Generate for all audited leads without email_objet
            rows = conn.execute("""
                SELECT lb.id, lb.nom, lb.ville, lb.category, lb.site_web, lb.email, lb.telephone,
                       lb.rating, lb.nb_avis,
                       la.mobile_score, la.score_seo, la.score_urgence, la.lcp_ms,
                       la.has_meta_description, la.has_contact_button, la.tel_link, la.cms_detected,
                       la.lien_rapport
                FROM leads_bruts lb
                JOIN leads_audites la ON la.lead_id = lb.id
                WHERE la.email_objet IS NULL OR la.email_objet = ''
            """).fetchall()
            
            generated = 0
            logger.error(f"[EMAIL GENERATE] Processing {len(rows)} rows")
            for row in rows:
                try:
                    # Build audit dict (16 champs: 0-15)
                    audit_dict = {
                        'lead_id': row[0],
                        'nom': row[1],
                        'ville': row[2],
                        'category': row[3],
                        'site_web': row[4],
                        'email': row[5],
                        'telephone': row[6],
                        'rating': row[7] or 0,
                        'nb_avis': row[8] or 0,
                        'mobile_score': row[9] or 0,
                        'score_seo': row[10] or 0,
                        'score_urgence': row[11] or 0,
                        'lcp_ms': row[12] or 0,
                        'has_meta_description': bool(row[13]) if row[13] is not None else True,
                        'has_contact_button': bool(row[14]) if row[14] is not None else True,
                        'tel_link': bool(row[15]) if row[15] is not None else True,
                        'cms_detected': row[16] or '',
                        'lien_rapport': row[17] or '',  # row[17] est la.lien_rapport
                    }
                    
                    profile = _determine_profile_v9(audit_dict)
                    audit_dict['profile'] = profile
                    audit_dict['prospect_nom'] = audit_dict['nom']
                    if not audit_dict.get('lien_rapport'):
                        audit_dict['lien_rapport'] = f"https://audit.incidenx.com/{re.sub(r'[^a-zA-Z0-9]', '-', audit_dict['nom'].lower())}"
                    
                    # Utiliser email_builder avec templates HTML (profil A, B, C, D)
                    sys.path.insert(0, os.path.join(ROOT, 'envoi'))
                    try:
                        from email_builder import build_premium_email
                        html_content = build_premium_email(audit_dict, verify_link=False)
                        # Objet basé sur le profil
                        profile = audit_dict.get('profile', 'A')
                        email_objet = f"Profil {profile} - Analyse pour {audit_dict['nom']}"
                        logger.error(f"[EMAIL GENERATE] Email builder OK: profile={profile}")
                    except Exception as eb_err:
                        logger.warning(f"Email builder indisponible, utilisation copywriter: {eb_err}")
                        # Fallback vers copywriter
                        sys.path.insert(0, os.path.join(ROOT, 'copywriter'))
                        try:
                            from copywriter.main import get_all_impacts, extract_problemes_detectes, determine_main_problem, generate_email_content
                            impacts = get_all_impacts(audit_dict)
                            problemes = extract_problemes_detectes(impacts, audit_dict)
                            main_prob = determine_main_problem(problemes, impacts) if problemes else {"service_propose": "Audit", "probleme_principal": "Analyse"}
                            copy_res = generate_email_content(audit_dict, main_prob)
                            email_objet = copy_res.get('email_objet') or f"Analyse pour {audit_dict['nom']}"
                            email_corps_raw = copy_res.get('email_corps', '') or ''
                            if email_corps_raw and not email_corps_raw.strip().startswith('<'):
                                html_content = '<!DOCTYPE html><html><head><meta charset="UTF-8"></head><body style="font-family: Arial, sans-serif; line-height: 1.6; padding: 20px;">' + email_corps_raw.replace('\n\n', '</p><p style="margin: 16px 0;">').replace('\n', '<br>') + '</body></html>'
                            else:
                                html_content = email_corps_raw
                        except Exception as cw_err:
                            html_content = f"<p>Erreur génération email pour {audit_dict['nom']}</p>"
                            email_objet = f"Analyse pour {audit_dict['nom']}"
                    
                    if not html_content:
                        html_content = f"<p>Erreur génération email pour {audit_dict['nom']}</p>"
                    
                    conn.execute("""
                        UPDATE leads_audites 
                        SET email_objet = ?, email_corps = ?, profile = ?
                        WHERE lead_id = ?
                    """, (email_objet, html_content, profile, row[0]))
                    
                    generated += 1
                    logger.error(f"[EMAIL GENERATE] SAVED: lead_id={row[0]}, email_objet={email_objet[:50] if email_objet else 'None'}...")
                except Exception as e2:
                    logger.error(f"Erreur génération email pour {row[1]}: {e2}")
            
            conn.commit()
        
        return jsonify({
            'statut': 'ok',
            'generated': generated,
            'message': f'{generated} email(s) gÃ©nÃ©rÃ©(s)'
        })
        
    except Exception as e:
        logger.error(f"POST /api/email/generate â {e}")
        return jsonify({'error': str(e)}), 500


# âââââââââââââââââââââââââââââââââââââââââââââââ
# POST /api/email/send  â SQLite + Resend
# âââââââââââââââââââââââââââââââââââââââââââââââ

@app.route('/api/email/send', methods=['POST'])
def api_email_send():
    """
    Envoie les emails approuvés via resend_sender.py.
    Enregistre chaque envoi dans SQLite (emails_envoyes).
    Body JSON : {lead_ids: [...]} — si vide, envoie tous les approuvés
    """
    global _email_job
    
    data     = request.get_json() or {}
    lead_ids = [l.strip().lower() for l in data.get('lead_ids', [])]

    if _email_job['running']:
        return jsonify({'error': 'Un envoi est déjà en cours'}), 409

    sys.path.insert(0, os.path.join(ROOT, 'envoi'))
    from resend_sender import send_prospecting_email
    # Note: On ne重构plus l'email - on utilise email_corps直接从 la base

    candidats = get_audits_ready_for_email()

    _email_job['running'] = True
    _email_job['total'] = 0
    _email_job['current'] = 0
    _email_job['success'] = 0
    _email_job['failed'] = 0
    _email_job['results'] = []

    def _run():
        global _email_job
        try:
            filtered = []
            for lead in candidats:
                lid = str(lead.get('lead_id'))
                if lead_ids and lid not in [str(x) for x in lead_ids]:
                    continue
                if not lead.get('approuve'):
                    continue
                filtered.append(lead)
            
            _email_job['total'] = len(filtered)
            
            for lead in filtered:
                _email_job['current'] += 1
                nom         = lead.get('nom', 'prospect')
                email       = lead.get('email', '').strip()
                email_objet = lead.get('email_objet', '').strip()
                email_corps = lead.get('email_corps', '').strip()
                lien        = lead.get('lien_rapport', '').strip()

                if not email or not email_corps:
                    _email_job['failed'] += 1
                    _email_job['results'].append({'nom': nom, 'statut': 'skip', 'raison': 'email ou corps manquant'})
                    continue

                try:
                    lien = lead.get('lien_rapport', '').strip()
                    if not lien:
                        lien = lead.get('site_web') or "https://audit.incidenx.com"
                    
                    # Utiliser l'email deja generee en base
                    email_corps_raw = email_corps
                    
                    # Wrapper en HTML si nécessaire (le copywriter génère du texte brut)
                    if email_corps_raw and not email_corps_raw.strip().startswith('<'):
                        # Convertir les sauts de ligne en <br> et wrapper en HTML
                        html_premium = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; padding: 20px;">
{email_corps_raw.replace('\n\n', '</p><p style="margin: 16px 0;">').replace('\n', '<br>')}
</body></html>"""
                    else:
                        html_premium = email_corps_raw
                    
                    # Verifier que le lien est toujours valide
                    if html_premium and lien:
                        try:
                            import requests
                            resp = requests.head(lien, timeout=5, allow_redirects=True)
                            if resp.status_code != 200:
                                logger.warning(f" Lien {lien} inaccessible ({resp.status_code}), l'email sera envoye tel quel")
                        except:
                            pass
                except Exception as e:
                    logger.error(f"Erreur preparation email({nom}): {e}")
                    html_premium = email_corps

                result = send_prospecting_email(
                    prospect_email=email,
                    prospect_nom=nom,
                    email_objet=email_objet,
                    email_corps=html_premium,
                    lien_rapport=lien,
                    dry_run=False
                )

                if result.get('success'):
                    try:
                        insert_email_sent({
                            'lead_id':          lead.get('lead_id'),
                            'message_id_resend': result.get('message_id', ''),
                            'email_objet':      email_objet,
                            'email_corps':      html_premium,
                            'email_destinataire': email,
                            'lien_rapport':     lien,
                            'statut_envoi':     'envoye',
                        })
                        _email_job['success'] += 1
                    except Exception as e:
                        logger.error(f"insert_email_sent({nom}): {e}")
                        _email_job['failed'] += 1
                else:
                    _email_job['failed'] += 1

                _email_job['results'].append({
                    'nom':        nom,
                    'email':      email,
                    'statut':     result.get('statut'),
                    'success':    result.get('success'),
                    'message_id': result.get('message_id', ''),
                    'erreur':     result.get('erreur', '')
                })
        except Exception as e:
            logger.error(f"Email job error: {e}")
        finally:
            _email_job['running'] = False

    threading.Thread(target=_run, daemon=True).start()

    return jsonify({'statut': 'lance', 'total': len(candidats)})


@app.route('/api/email/status')
def api_email_status():
    """Retourne le statut de l'envoi en cours."""
    return jsonify({
        'running':   _email_job['running'],
        'total':     _email_job['total'],
        'current':   _email_job['current'],
        'success':   _email_job['success'],
        'failed':    _email_job['failed'],
    })


# POST /api/email/test

# POST /api/email/test  â Envoi email test vers soi-mÃªme
# ââââââââââââââââââââââââââââââââââââââââââââââââââââ

@app.route('/api/email/test', methods=['POST'])
def api_email_test():
    """
    Envoie un email test Ã  jmedansi@incidenx.com pour prÃ©visualisation.
    Body JSON : {objet: "...", corps: "...", lead_id: optional}
    """
    try:
        data = request.get_json() or {}
        objet = data.get('objet', '').strip()
        corps = data.get('corps', '').strip()
        lead_id = data.get('lead_id')
        logger.error(f"[V16 DEBUG] api_email_test RECUE lead_id={lead_id} type={type(lead_id)}")

        # Import resend_sender
        sys.path.insert(0, os.path.join(ROOT, 'envoi'))
        from resend_sender import send_prospecting_email

        # Si lead_id fourni, récupérer l'email depuis la base
        if lead_id:
            from database.db_manager import get_conn
            with get_conn() as conn:
                row = conn.execute('SELECT email_objet, email_corps FROM leads_audites WHERE lead_id = ?', (lead_id,)).fetchone()
                if row:
                    objet = row[0] or objet
                    corps = row[1] or corps

        if not objet or not corps:
            return jsonify({'error': 'objet et corps requis'}), 400

        # Wrapper en HTML si nécessaire
        if not corps.strip().startswith('<'):
            html_premium = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; padding: 20px;">
{corps.replace('\n\n', '</p><p style="margin: 16px 0;">').replace('\n', '<br>')}
</body></html>"""
        else:
            html_premium = corps

        # Envoi vers soi-mÃªme
        test_recipient = data.get('destinataire') or os.getenv("BREVO_SENDER_EMAIL")
        prospect_name = data.get('prospect_nom', 'Test')
        
        # Get lien_rapport from DB if available
        lien_rapport = data.get('lien_rapport', '')
        if lead_id:
            from database.db_manager import get_conn
            with get_conn() as conn:
                row = conn.execute('SELECT lien_rapport FROM leads_audites WHERE lead_id = ?', (lead_id,)).fetchone()
                if row and row[0]:
                    lien_rapport = row[0]
        
        result = send_prospecting_email(
            prospect_email=test_recipient,
            prospect_nom=prospect_name,
            email_objet=objet,
            email_corps=html_premium,
            lien_rapport=lien_rapport,
            dry_run=False
        )

        if result.get('success'):
            # Enregistrer dans la base pour suivi
            try:
                from database.db_manager import insert_email_sent
                insert_email_sent({
                    'lead_id': lead_id,
                    'message_id_resend': result.get('message_id', ''),
                    'email_objet': objet,
                    'email_corps': html_premium,
                    'lien_rapport': lien_rapport,
                    'email_destinataire': test_recipient,
                    'statut_envoi': 'test',
                })
            except Exception as e:
                logger.error(f"insert_email_sent(test): {e}")

            return jsonify({
                'success': True,
                'message_id': result.get('message_id', ''),
                'sent_to': test_recipient
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('erreur', 'Erreur envoi')
            }), 500

    except Exception as e:
        logger.error(f"POST /api/email/test â {e}")
        return jsonify({'error': str(e)}), 500


# âââââââââââââââââââââââââââââââââââââââââââââââââââ
# SYNC SHEETS EN ARRIÃRE-PLAN (toutes les heures)
# âââââââââââââââââââââââââââââââââââââââââââââââ

def _sync_worker():
    """Thread de synchronisation SQLite â Google Sheets (toutes les heures)."""
    time.sleep(300)  # DÃ©lai initial de 5 minutes aprÃ¨s dÃ©marrage
    while True:
        try:
            from database.sheets_sync import sync_to_sheets
            sync_to_sheets()
        except Exception as e:
            logger.error(f"sync_worker â {e}")
            print(f"[Sync] Erreur : {e}")
        time.sleep(3600)  # Toutes les heures


# âââââââââââââââââââââââââââââââââââââââââââââââ
# --------------------------------------------------------------------------------
# LANCEMENT
# --------------------------------------------------------------------------------

if __name__ == '__main__':
    print("\n" + "="*55)
    print("  Incidenx - Prospection Machine Dashboard")
    print("  http://localhost:5001")
    print("  Source de donnees : SQLite (data/prospection.db)")
    print("="*55 + "\n")
    
    # Lancer le thread de synchronisation Sheets en arriÃ¨re-plan
    sync_thread = threading.Thread(target=_sync_worker, daemon=True)
    sync_thread.start()
    print("  [Sync] Thread de synchronisation Sheets dÃ©marrÃ© (toutes les heures)")
    
    app.run(host='127.0.0.1', port=5001, debug=True)
