# -*- coding: utf-8 -*-
"""
dashboard/app.py — Serveur Flask du cockpit Incidenx
SQLite comme source de vérité principale.
Sheets est synchronisé toutes les heures en arrière-plan.
Lance : python dashboard/app.py
Port  : 5001
"""




# === ROUTE API LEADS (tableau principal) ===
# (À placer après l'initialisation de l'app Flask)

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
from functools import lru_cache
import re
from datetime import datetime

PYTHONW = r"C:\Python314\pythonw.exe" if sys.platform == 'win32' else sys.executable
CREATE_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0
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
STATIC_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=STATIC_DIR, static_url_path='/static')

# --- Configuration CORS ---
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response


# Route pour servir le dashboard HTML principal
@app.route('/')
def dashboard_root():
    return send_from_directory(STATIC_DIR, 'dashboard-v4.html')

# === ROUTE API LEADS (tableau principal) ===
@app.route('/api/leads')
def api_leads():
    from database.db_manager import get_all_leads
    # Récupération des filtres GET
    statut = request.args.get('statut', 'tous')
    site = request.args.get('site', 'tous')
    email = request.args.get('email', 'tous')
    note = request.args.get('note', 'tous')
    sector = request.args.get('sector', 'tous')
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 50))

    # Récupération brute
    all_leads = get_all_leads(statut=statut, limit=10000)

    # Filtres additionnels côté Python (site, email, note, sector)
    def lead_filter(l):
        if site != 'tous':
            has_site = bool(l.get('site_web'))
            if (site == 'avec' and not has_site) or (site == 'sans' and has_site):
                return False
        if email != 'tous':
            has_email = bool(l.get('email'))
            if (email == 'avec' and not has_email) or (email == 'sans' and has_email):
                return False
        if note != 'tous':
            try:
                n = float(l.get('rating') or 0)
                if note == 'bons' and n < 4:
                    return False
                if note == 'mauvais' and n >= 4:
                    return False
            except Exception:
                return False
        if sector != 'tous':
            if (l.get('category') or '').lower() != sector.lower():
                return False
        return True

    filtered = [l for l in all_leads if lead_filter(l)]
    total = len(filtered)
    total_pages = max(1, (total + limit - 1) // limit)
    page = max(1, min(page, total_pages))
    start = (page - 1) * limit
    end = start + limit
    leads_page = filtered[start:end]

    # Adapter les champs pour le frontend (exemple minimal)
    def adapt(l):
        return {
            'id': l.get('id'),
            'nom': l.get('nom'),
            'ville': l.get('ville'),
            'secteur': l.get('category'),
            'note': l.get('rating'),
            'avis': l.get('nb_avis'),
            'site_web': l.get('site_web'),
            'email': l.get('email'),
            'statut': l.get('statut'),
            'score_urgence': l.get('score_urgence'),
            'a_site': bool(l.get('site_web')),
            'a_email': bool(l.get('email')),
        }

    return jsonify({
        'leads': [adapt(l) for l in leads_page],
        'page': page,
        'total_pages': total_pages,
        'total': total
    })


def _safe_int(value, default=None):
    """Convertit une valeur en entier en toute sécurité."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


# --- Logging (un seul appel, au niveau WARNING pour les erreurs)
logging.basicConfig(
    filename=os.path.join(ROOT, 'errors.log'),
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# âââââââââââââââââââââââââââââââââââââââââââââââ
# WEBHOOK RESEND - TRACKING DES EMAILS

import json
from datetime import datetime

# --- WEBHOOK RESEND: Enregistre tous les événements Resend dans email_events et met à jour les champs tracking ---
from envoi.email_tracking_service import EmailTrackingService

# Redirection pour les webhooks Resend (sans /prospection/)
@app.route('/webhooks/resend', methods=['POST'])
def webhook_resend_root():
    """Rediriger vers le webhook avec /prospection/"""
    from flask import redirect, request
    # Appeler directement la fonction webhook
    return webhook_resend()

@app.route('/prospection/webhooks/resend', methods=['POST'])
def webhook_resend():
    """
    Webhook Resend - Enregistrer TOUS les événements dans email_events et mettre à jour emails_envoyes
    """
    # Valider la signature du webhook avec Svix
    from svix.webhooks import Webhook

    RESEND_WEBHOOK_SECRET = os.getenv('RESEND_WEBHOOK_SECRET', '')

    if not RESEND_WEBHOOK_SECRET:
        logger.error("RESEND_WEBHOOK_SECRET not configured")
        return jsonify({'error': 'Webhook secret not configured'}), 500

    try:
        # Récupérer le raw body pour la validation
        body = request.get_data(as_text=True)
        headers = dict(request.headers)

        # Valider avec Svix
        wh = Webhook(RESEND_WEBHOOK_SECRET)
        data = wh.verify(body, headers)

        logger.info(f"✅ Webhook valide de Resend: {data.get('type')}")
    except Exception as e:
        logger.error(f"❌ Erreur validation webhook: {e}")
        return jsonify({'error': 'Invalid signature'}), 401

    event_type = data.get('type')  # 'email.sent', 'email.opened', 'email.clicked', etc.

    # Resend webhook format: {"type": "email.opened", "data": {"email_id": "re_xxx", ...}}
    resend_data = data.get('data') or {}
    message_id = (resend_data.get('email_id')
                  or data.get('email_record_id')
                  or data.get('message_id'))

    timestamp = resend_data.get('created_at') or data.get('timestamp') or datetime.utcnow().isoformat()
    event_type_clean = event_type.split('.')[-1] if event_type else 'unknown'

    meta = {
        'user_agent': resend_data.get('user_agent') or data.get('user_agent'),
        'ip': resend_data.get('ip') or data.get('ip'),
        'details': resend_data,
        'raw': data
    }
    # Log event in email_events
    try:
        EmailTrackingService.log_event(
            message_id=message_id,
            event_type=event_type_clean,
            timestamp=timestamp,
            meta=meta
        )
    except Exception as e:
        logger.error(f"[webhook_resend] log_event failed: {e}")
    # Update tracking fields in emails_envoyes
    try:
        if event_type_clean == 'opened':
            _handle_email_opened(message_id, timestamp, meta)
        elif event_type_clean == 'clicked':
            _handle_email_clicked(message_id, timestamp, meta)
        elif event_type_clean in ('bounced', 'complained', 'spam', 'blocked'):
            _handle_email_bounced(message_id, timestamp, meta)
    except Exception as e:
        logger.error(f"[webhook_resend] tracking update failed: {e}")
    return jsonify({'status': 'ok'})

# --- Handlers for tracking updates ---
def _handle_email_opened(message_id, timestamp, meta):
    try:
        EmailTrackingService.mark_opened(message_id, timestamp, meta)
    except Exception as e:
        logger.error(f"[handle_email_opened] {e}")

def _handle_email_clicked(message_id, timestamp, meta):
    try:
        EmailTrackingService.mark_clicked(message_id, timestamp, meta)
    except Exception as e:
        logger.error(f"[handle_email_clicked] {e}")

def _handle_email_bounced(message_id, timestamp, meta):
    try:
        EmailTrackingService.mark_bounced(message_id, timestamp, meta)
    except Exception as e:
        logger.error(f"[handle_email_bounced] {e}")

# --- DEBUG: Voir les derniers webhooks reçus ---
@app.route('/api/webhook-debug')
def webhook_debug():
    """Voir les derniers événements reçus pour déboguer."""
    from database.db_manager import get_conn
    try:
        with get_conn() as conn:
            # Derniers événements
            events = conn.execute("""
                SELECT ee.event_type, ee.timestamp, ee.email_record_id,
                       e.email_destinataire, e.message_id_resend
                FROM email_events ee
                LEFT JOIN emails_envoyes e ON ee.email_record_id = e.id
                ORDER BY ee.timestamp DESC
                LIMIT 50
            """).fetchall()

            # Statistiques par type
            stats = conn.execute("""
                SELECT event_type, COUNT(*) as count
                FROM email_events
                GROUP BY event_type
                ORDER BY count DESC
            """).fetchall()

        return jsonify({
            'total_events': sum(s[1] for s in stats),
            'stats_by_type': {s[0]: s[1] for s in stats},
            'recent_events': [
                {
                    'event_type': r[0],
                    'timestamp': r[1],
                    'email_record_id': r[2],
                    'email_destinataire': r[3],
                    'message_id_resend': r[4]
                }
                for r in events
            ]
        })
    except Exception as e:
        logger.error(f"webhook_debug error: {e}")
        return jsonify({'error': str(e)}), 500
# âââââââââââââââââââââââââââââââââââââââââââââââ
# GET /api/stats  â SQLite
# âââââââââââââââââââââââââââââââââââââââââââââââ
# GET /api/emails  â SQLite
# âââââââââââââââââââââââââââââââââââââââââââââââ
# GET /api/leads  â SQLite
# âââââââââââââââââââââââââââââââââââââââââââââââ
# UPDATE & DELETE LEADS  â SQLite
# âââââââââââââââââââââââââââââââââââââââââââââââ
# GET /api/emails  â SQLite
# âââââââââââââââââââââââââââââââââââââââââââââââ
# GET /api/rapports  â SQLite
# âââââââââââââââââââââââââââââââââââââââââââââââ
# GET /api/crm  â SQLite
# âââââââââââââââââââââââââââââââââââââââââââââââ
# POST /api/crm/update  â SQLite
# âââââââââââââââââââââââââââââââââââââââââââââââ
# GET /api/stats - SQLite
@app.route('/api/stats')
def api_stats():
    try:
        campaign_id = request.args.get('campaign_id', type=int)
        campaign_ids = request.args.get('campaign_ids')
        date_start = request.args.get('date_start')
        date_end = request.args.get('date_end')

        stats = get_dashboard_stats(
            campaign_id=campaign_id,
            date_start=date_start,
            date_end=date_end,
            campaign_ids=campaign_ids
        )

        # Wrapper les données avec la structure attendue par le frontend
        response = {
            'pipeline': {
                'leads_scrapes': stats.get('leads_scrapes', 0),
                'leads_audites': stats.get('leads_audites', 0),
                'emails_prets': stats.get('emails_prets', 0),
                'envoyes': stats.get('envoyes', 0)
            },
            'performance': {
                'score_moyen': stats.get('score_moyen', 0),
                'mobile_moyen': stats.get('mobile_moyen', 0),
                'seo_moyen': stats.get('seo_moyen', 0)
            },
            'email_stats': {
                'nb_envoyes': stats.get('nb_envoyes', 0),
                'taux_ouverture': stats.get('taux_ouverture', 0),
                'taux_clic': stats.get('taux_clic', 0),
                'taux_reponse': stats.get('taux_reponse', 0),
                'reponses_positives': stats.get('reponses_positives', 0),
                'rdv_obtenus': stats.get('rdv_obtenus', 0),
                'bounces': stats.get('bounces', 0),
                'spam': stats.get('spam', 0)
            },
            **stats  # Inclure toutes les autres propriétés directement
        }
        return jsonify(response)
    except Exception as e:
        logger.error(f"GET /api/stats → {e}")
        return jsonify({'error': str(e)}), 500


# GET /api/campaigns - SQLite
@app.route('/api/campaigns')
def api_campaigns():
    try:
        date_start = request.args.get('date_start')
        date_end = request.args.get('date_end')

        campaigns = get_all_campaigns(date_start=date_start, date_end=date_end)
        return jsonify({'campaigns': campaigns})
    except Exception as e:
        logger.error(f"GET /api/campaigns → {e}")
        return jsonify({'error': str(e)}), 500


# GET /api/config - SQLite
@app.route('/api/config')
def api_config():
    try:
        resend_configured = bool(os.getenv('RESEND_API_KEY'))
        brevo_configured = bool(os.getenv('BREVO_API_KEY'))
        groq_configured = bool(os.getenv('GROQ_API_KEY'))

        provider_name = 'Resend' if resend_configured else ('Brevo' if brevo_configured else 'None')

        return jsonify({
            'resend_configured': resend_configured,
            'brevo_configured': brevo_configured,
            'groq_configured': groq_configured,
            'provider_name': provider_name
        })
    except Exception as e:
        logger.error(f"GET /api/config → {e}")
        return jsonify({'error': str(e)}), 500


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
# âââââââââââââââââââââââââââââââââââââââââââââââ

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
                # Générer le slug aligné sur generate_slug() Python ET makeSlug() JS
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
            # Ne pas écraser 'total' s'il a déjà été fixé par lead_names/lead_ids/limit
            if not _audit_job.get('total'):
                _audit_job['total']  = 0
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
                    # Compteur de succès — détecter plusieurs variantes (encodage Windows)
                    _line_lower = line_s.lower()
                    if ('[sqlite] audit' in _line_lower and 'enregistr' in _line_lower) \
                       or ('audit enregistr' in _line_lower) \
                       or ('[ok] audit enregistr' in _line_lower):
                        _audit_job['current'] += 1
                    # Compteur d'échecs
                    elif 'echoue' in _line_lower or 'audit_echoue' in _line_lower \
                         or 'ÉCHOUÉ'.lower() in _line_lower or '[erreur] complet' in _line_lower:
                        _audit_job['failed'] += 1
                        _audit_job['current'] += 1  # compte quand même
                    elif ('termin' in _line_lower and 'audit' in _line_lower) or ('Terminé' in line_s and 'Audit' in line_s):
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
# âââââââââââââââââââââââââââââââââââââââââââââââ
# --------------------------------------------------------------------------------
# LANCEMENT
# --------------------------------------------------------------------------------



# ─────────────────────────────────────────────────────────────────
# PLANIFICATEUR
# ─────────────────────────────────────────────────────────────────

@app.route("/api/planning", methods=["GET"])
def api_planning_list():
    try:
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT * FROM planned_campaigns
                ORDER BY date_planifiee ASC, heure ASC
            """).fetchall()
        return jsonify({"campaigns": [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/planning", methods=["POST"])
def api_planning_add():
    try:
        data    = request.get_json() or {}
        secteur = data.get("secteur", "").strip()
        keyword = data.get("keyword", "").strip()
        city    = data.get("city", "").strip()
        limit   = int(data.get("limit_leads", 50))
        date_p  = data.get("date_planifiee", "")
        heure   = data.get("heure", "09:00")
        if not keyword or not city or not date_p:
            return jsonify({"error": "keyword, city et date_planifiee requis"}), 400
        with get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO planned_campaigns (secteur, keyword, city, limit_leads, date_planifiee, heure) VALUES (?,?,?,?,?,?)",
                (secteur, keyword, city, limit, date_p, heure)
            )
            conn.commit()
            new_id = cur.lastrowid
        return jsonify({"success": True, "id": new_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/planning/<int:pid>", methods=["DELETE"])
def api_planning_delete(pid):
    try:
        with get_conn() as conn:
            conn.execute("UPDATE planned_campaigns SET statut='cancelled' WHERE id=?", (pid,))
            conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/planning/<int:pid>/launch", methods=["POST"])
def api_planning_launch_now(pid):
    try:
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM planned_campaigns WHERE id=?", (pid,)).fetchone()
        if not row:
            return jsonify({"error": "Introuvable"}), 404
        c = dict(row)
        from datetime import date as _date
        campaign_name = f"{c["secteur"]} {c["city"]} {_date.today().isoformat()}"
        camp_id = insert_campaign(campaign_name, c["secteur"] or c["keyword"], c["city"], nb_demande=c["limit_leads"])
        min_e = c.get("min_emails") or c.get("limit_leads") or 20
        cmd = [PYTHONW, os.path.join(ROOT, "scraper", "main.py"),
               "--keyword", c["keyword"], "--city", c["city"],
               "--limit", str(min_e * 4),
               "--min-emails", str(min_e),
               "--campaign-id", str(camp_id)]
        CREATE_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0
        subprocess.Popen(cmd, cwd=ROOT, creationflags=CREATE_NO_WINDOW,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with get_conn() as conn:
            conn.execute("UPDATE planned_campaigns SET statut='running', campaign_id=? WHERE id=?", (camp_id, pid))
            conn.commit()
        return jsonify({"success": True, "campaign_id": camp_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/planning/quota", methods=["GET"])
def api_planning_quota():
    try:
        from scheduler import get_daily_quota, get_emails_sent_today
        quota = get_daily_quota()
        sent  = get_emails_sent_today()
        return jsonify({"quota": quota, "sent": sent, "remaining": max(0, quota - sent)})
    except Exception:
        return jsonify({"quota": 100, "sent": 0, "remaining": 100})


@app.route("/api/planning/quota", methods=["POST"])
def api_planning_quota_update():
    try:
        data  = request.get_json() or {}
        quota = max(1, min(300, int(data.get("daily_quota", 30))))
        with get_conn() as conn:
            conn.execute("UPDATE planning_settings SET value=? WHERE key='daily_quota'", (str(quota),))
            conn.commit()
        return jsonify({"success": True, "daily_quota": quota})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/planning/niche-stats", methods=["GET"])
def api_planning_niche_stats():
    try:
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT c.secteur as niche,
                       COUNT(DISTINCT c.id) AS campagnes,
                       COALESCE(SUM(c.leads_total), 0) AS leads_scrapes,
                       COALESCE(SUM(c.emails_envoyes), 0) AS emails_envoyes,
                       COALESCE(SUM(c.nb_reponses), 0) AS nb_reponses
                FROM campagnes c
                WHERE c.secteur IS NOT NULL AND c.secteur != ""
                GROUP BY c.secteur ORDER BY emails_envoyes DESC
            """).fetchall()
        return jsonify({"stats": [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/scraping-priorities", methods=["GET"])
def api_get_scraping_priorities():
    try:
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT id, secteur, keyword, ville, limit_leads, priorite,
                       actif, frequence_jours, derniere_execution
                FROM scraping_priorities
                ORDER BY priorite ASC, secteur ASC, ville ASC
            """).fetchall()
        return jsonify({"priorities": [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/scraping-priorities", methods=["POST"])
def api_add_scraping_priority():
    try:
        d = request.get_json() or {}
        with get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO scraping_priorities
                    (secteur, keyword, ville, limit_leads, priorite, frequence_jours, actif)
                VALUES (:secteur, :keyword, :ville, :limit_leads, :priorite, :frequence_jours, 1)
            """, {
                'secteur':        d.get('secteur', 'default'),
                'keyword':        d['keyword'],
                'ville':          d['ville'],
                'limit_leads':    int(d.get('limit_leads', 50)),
                'priorite':       int(d.get('priorite', 5)),
                'frequence_jours':int(d.get('frequence_jours', 30)),
            })
            conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/scraping-priorities/<int:pid>", methods=["DELETE"])
def api_delete_scraping_priority(pid):
    try:
        with get_conn() as conn:
            conn.execute("DELETE FROM scraping_priorities WHERE id=?", (pid,))
            conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/scraping-priorities/<int:pid>/toggle", methods=["POST"])
def api_toggle_scraping_priority(pid):
    try:
        with get_conn() as conn:
            conn.execute(
                "UPDATE scraping_priorities SET actif = 1 - actif WHERE id=?", (pid,)
            )
            conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/auto-plan/now", methods=["POST"])
def api_auto_plan_now():
    """Déclenche l'auto-planification manuellement."""
    try:
        from auto_planner import run_auto_plan, plan_week, plan_day
        data  = request.get_json() or {}
        mode  = data.get('mode', 'day')
        force = data.get('force', False)
        if mode == 'week':
            results = plan_week()
            total = sum(results.values())
            return jsonify({"ok": True, "mode": "week", "added": total, "details": results})
        else:
            added = plan_day(force=force) if force else run_auto_plan()
            return jsonify({"ok": True, "mode": "day", "added": added})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/auto-plan/backlog", methods=["GET"])
def api_auto_plan_backlog():
    """Retourne l'état du backlog pour affichage dans le dashboard."""
    try:
        from auto_planner import get_pipeline_backlog, get_auto_plan_settings
        backlog   = get_pipeline_backlog()
        settings  = get_auto_plan_settings()
        daily_quota = settings['daily_quota']
        backlog_days = round(backlog.get('leads_with_email', 0) / max(daily_quota, 1), 1)
        return jsonify({
            **backlog,
            "backlog_days":   backlog_days,
            "daily_quota":    daily_quota,
            "max_backlog_days": settings['max_backlog_days'],
            "status": (
                "paused"   if backlog_days >= settings['max_backlog_days']     else
                "slow"     if backlog_days >= settings['max_backlog_days'] - 1 else
                "normal"
            )
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/emails/send-batch", methods=["POST"])
def api_emails_send_batch():
    try:
        from scheduler import get_quota_remaining
        data  = request.get_json() or {}
        limit = min(int(data.get("limit", 10)), get_quota_remaining())
        if limit <= 0:
            return jsonify({"sent": 0, "reason": "quota_atteint"})
        with get_conn() as conn:
            leads = conn.execute("""
                SELECT lb.id FROM leads_bruts lb
                JOIN leads_audites la ON la.lead_id = lb.id
                WHERE lb.email IS NOT NULL AND lb.email != ""
                  AND la.approuve = 1
                  AND lb.statut NOT IN ('envoye', 'email_sent')
                  AND lb.id NOT IN (SELECT DISTINCT lead_id FROM emails_envoyes WHERE lead_id IS NOT NULL)
                ORDER BY la.score_urgence DESC LIMIT ?
            """, (limit,)).fetchall()
        sent = 0
        for lead in leads:
            try:
                cmd = [sys.executable, os.path.join(ROOT, "envoi", "resend_sender.py"), "--lead-id", str(lead["id"])]
                result = subprocess.run(cmd, cwd=ROOT, capture_output=True, timeout=30)
                if result.returncode == 0:
                    sent += 1
            except Exception:
                pass
        return jsonify({"sent": sent, "attempted": len(leads)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/review")
def pipeline_review():
    """Page de review d'un batch pipeline : audits + emails à valider."""
    ids_param = request.args.get("ids", "")
    try:
        lead_ids = [int(x) for x in ids_param.split(",") if x.strip().isdigit()]
    except Exception:
        lead_ids = []

    if not lead_ids:
        return "<h2>Aucun lead spécifié.</h2>", 400

    leads = []
    with get_conn() as conn:
        for lid in lead_ids:
            row = conn.execute("""
                SELECT lb.id, lb.nom, lb.email, lb.site_web, lb.rating, lb.nb_avis,
                       la.probleme_principal, la.score_urgence,
                       la.email_objet, la.email_corps, la.lien_rapport,
                       la.score_performance, la.score_seo
                FROM leads_bruts lb
                JOIN leads_audites la ON lb.id = la.lead_id
                WHERE lb.id = ?
            """, (lid,)).fetchone()
            if row:
                d = dict(row)
                lien = d.get("lien_rapport") or ""
                if lien.startswith("local://"):
                    slug = lien.replace("local://", "").strip("/")
                    d["preview_url"] = f"/previews/{slug}/"
                elif lien.startswith("http"):
                    d["preview_url"] = lien
                else:
                    d["preview_url"] = None
                leads.append(d)

    total = len(leads)
    from markupsafe import escape

    rows_html = ""
    for i, l in enumerate(leads, 1):
        rapport_btn = (
            f'<a href="{escape(l["preview_url"])}" target="_blank" class="btn-rapport">Voir rapport</a>'
            if l["preview_url"] else '<span class="no-rapport">—</span>'
        )
        corps = (l.get("email_corps") or "").replace("`", "&#96;").replace("</", "&lt;/")
        rows_html += f"""
        <div class="lead-card">
          <div class="lead-header">
            <span class="lead-num">{i}</span>
            <div class="lead-info">
              <strong>{escape(l['nom'])}</strong>
              <span class="lead-email">{escape(l['email'] or '—')}</span>
            </div>
            <div class="lead-scores">
              <span class="badge urgence">⚡ {l['score_urgence'] or '?'}/10</span>
              {'<span class="badge rating">⭐ ' + str(l['rating'] or '') + ' (' + str(l['nb_avis'] or 0) + ' avis)</span>' if l.get('rating') else ''}
            </div>
            {rapport_btn}
          </div>
          <div class="lead-problem">{escape(l['probleme_principal'] or 'Non défini')}</div>
          <div class="email-subject">📧 <em>{escape(l['email_objet'] or '—')}</em></div>
          <details class="email-body">
            <summary>Voir le corps du mail</summary>
            <pre>{corps}</pre>
          </details>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Review Pipeline — {total} leads</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #0c2832; color: #d0e8ec; padding: 20px; }}
    h1 {{ font-size: 1.4rem; margin-bottom: 6px; color: #e8f4f7; }}
    .subtitle {{ color: #6a9aaa; font-size: .85rem; margin-bottom: 20px; }}
    .lead-card {{ background: #0f3040; border: 1px solid #1a4a5a; border-radius: 10px;
                  padding: 14px 16px; margin-bottom: 12px; }}
    .lead-header {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 8px; }}
    .lead-num {{ background: #1a4a5a; color: #7ab8c8; border-radius: 50%;
                 width: 26px; height: 26px; display: flex; align-items: center;
                 justify-content: center; font-size: .75rem; flex-shrink: 0; }}
    .lead-info {{ flex: 1; }}
    .lead-info strong {{ display: block; font-size: .95rem; color: #e8f4f7; }}
    .lead-email {{ font-size: .78rem; color: #6a9aaa; }}
    .lead-scores {{ display: flex; gap: 6px; flex-wrap: wrap; }}
    .badge {{ font-size: .72rem; padding: 2px 8px; border-radius: 20px; }}
    .badge.urgence {{ background: #3a1a1a; color: #ff8a7a; }}
    .badge.rating {{ background: #0f3a2a; color: #7adca8; }}
    .btn-rapport {{ background: #1a5a6a; color: #7ad4e8; border: 1px solid #2a7a8a;
                    padding: 4px 12px; border-radius: 6px; font-size: .78rem;
                    text-decoration: none; white-space: nowrap; }}
    .btn-rapport:hover {{ background: #2a7a8a; }}
    .no-rapport {{ color: #3a6a7a; font-size: .78rem; }}
    .lead-problem {{ font-size: .82rem; color: #f0c060; margin-bottom: 6px;
                     padding: 4px 8px; background: #1a2a10; border-radius: 4px; }}
    .email-subject {{ font-size: .83rem; color: #8ab8c8; margin-bottom: 6px; }}
    .email-body summary {{ font-size: .78rem; color: #4a8a9a; cursor: pointer; margin-top: 4px; }}
    .email-body summary:hover {{ color: #7ab8c8; }}
    .email-body pre {{ margin-top: 8px; font-size: .78rem; white-space: pre-wrap;
                       color: #a8d0da; background: #081e28; padding: 10px;
                       border-radius: 6px; border: 1px solid #1a4a5a; }}
  </style>
</head>
<body>
  <h1>Review Pipeline — {total} leads</h1>
  <p class="subtitle">Validés ce soir · Envoi demain 10h + 14h</p>
  {rows_html}
</body>
</html>"""
    return html


@app.route('/api/scraper/fill-quota', methods=['POST'])
def api_fill_quota():
    """Lance un top-up scraping si le pipeline est en dessous du quota journalier."""
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from auto_planner import fill_quota_if_needed, get_pipeline_count, get_auto_plan_settings
        settings = get_auto_plan_settings()
        pipeline = get_pipeline_count()
        deficit = max(0, settings['daily_quota'] - pipeline)
        if deficit == 0:
            return jsonify({'success': True, 'message': f'Quota atteint ({pipeline}/{settings["daily_quota"]})', 'deficit': 0})
        fill_quota_if_needed(trigger_immediate=True)
        return jsonify({'success': True, 'deficit': deficit, 'pipeline': pipeline, 'quota': settings['daily_quota']})
    except Exception as e:
        logger.error(f"POST /api/scraper/fill-quota → {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/bounces/check', methods=['POST'])
def api_check_bounces():
    """Interroge Resend pour mettre à jour les statuts bounce/spam dans la DB."""
    try:
        from envoi.resend_sender import check_bounces
        stats = check_bounces()
        if "error" in stats:
            return jsonify({'success': False, 'error': stats['error']}), 400
        return jsonify({'success': True, **stats})
    except Exception as e:
        logger.error(f"POST /api/bounces/check → {e}")
        return jsonify({'error': str(e)}), 500


# ===========================================================
# MODULE 5 : ANALYTICS & BUSINESS INTELLIGENCE
# ===========================================================

@app.route('/api/stats/funnel')
def api_stats_funnel():
    """Renvoie les données de l'entonnoir de prospection (Funnel)."""
    try:
        from database.db_manager import get_conn
        with get_conn() as conn:
            stats = conn.execute("""
                SELECT 
                    (SELECT COUNT(*) FROM leads_bruts) as total_scraped,
                    (SELECT COUNT(*) FROM leads_audites) as total_audited,
                    (SELECT COUNT(*) FROM emails_envoyes) as total_sent,
                    (SELECT SUM(clique) FROM emails_envoyes) as total_clicked,
                    (SELECT SUM(repondu) FROM emails_envoyes) as total_replied,
                    (SELECT SUM(rdv_confirme) FROM emails_envoyes) as total_rdv
            """).fetchone()
            return jsonify(dict(stats))
    except Exception as e:
        logger.error(f"Erreur API Funnel: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats/niche')
def api_stats_niche():
    """Renvoie les performances par secteur/ville."""
    try:
        from database.db_manager import get_niche_performance
        niches = get_niche_performance()
        return jsonify([dict(n) for n in niches])
    except Exception as e:
        logger.error(f"Erreur API Niche: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats/export')
def api_stats_export():
    """Exporte les performances en CSV."""
    import csv, io
    from flask import make_response
    try:
        from database.db_manager import get_conn
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT ee.email_destinataire, lb.nom, lb.ville, lb.category, 
                       ee.date_envoi, ee.ouvert, ee.clique, ee.repondu, ee.rdv_confirme
                FROM emails_envoyes ee
                JOIN leads_bruts lb ON ee.lead_id = lb.id
            """).fetchall()

        si = io.StringIO()
        cw = csv.writer(si)
        cw.writerow(['Email', 'Nom', 'Ville', 'Secteur', 'Date Envoi', 'Ouvert', 'Cliqué', 'Répondu', 'RDV'])
        for r in rows:
            cw.writerow(list(r))
            
        output = make_response(si.getvalue())
        output.headers["Content-Disposition"] = "attachment; filename=export_prospection.csv"
        output.headers["Content-type"] = "text/csv"
        return output
    except Exception as e:
        logger.error(f"Erreur Export CSV: {e}")
        return str(e), 500

@app.route('/api/stats/ab_test')
def api_stats_ab_test():
    """Renvoie l'analyse A/B Testing."""
    try:
        from database.db_manager import get_ab_test_performance
        results = get_ab_test_performance()
        return jsonify([dict(r) for r in results])
    except Exception as e:
        logger.error(f"Erreur API AB Test: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("\n" + "="*55)
    print("  Incidenx - Prospection Machine Dashboard")
    print("  http://localhost:5001")
    print("  Source de donnees : SQLite (data/prospection.db)")
    print("="*55 + "\n")

    # Scheduler planificateur
    try:
        from scheduler import init_scheduler
        init_scheduler()
        print("  [Scheduler] Planificateur démarré (scraping 08h, emails 9h-18h)")
    except Exception as _se:
        print(f"  [Scheduler] Non démarré : {_se}")


    def _sync_worker():
        import time
        while True:
            time.sleep(60)

    sync_thread = threading.Thread(target=_sync_worker, daemon=True)
    sync_thread.start()

    app.run(host='127.0.0.1', port=5001, debug=False)
