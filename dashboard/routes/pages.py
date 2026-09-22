# -*- coding: utf-8 -*-
"""
dashboard/routes/pages.py
Routes pour servir l'interface statique et la configuration de base.
"""
import os
from flask import Blueprint, send_from_directory, jsonify, request, render_template

pages_bp = Blueprint('pages', __name__, template_folder='../templates')

STATIC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

@pages_bp.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory(STATIC_DIR, filename)

@pages_bp.route('/')
def dashboard_root():
    """Dashboard V6 — interface 100 % modèle v2 (campagnes/listes/prospects).
    L'interface V5 (pipeline v1) est décommissionnée — /legacy renvoie 410 Gone."""
    return render_template('views/dashboard_v6.html')


@pages_bp.route('/legacy')
def dashboard_legacy():
    """Ancienne interface V5 — décommissionnée (pipeline v1 désactivé)."""
    return jsonify({
        "error": "V5 décommissionnée",
        "code": 410,
        "detail": "L'interface V5 (pipeline v1) a été désactivée. Utilisez le dashboard "
                   "V6 (/) — modèle Campagne → Liste → Prospect."
    }), 410

@pages_bp.route('/guide')
def serve_guide():
    return send_from_directory(os.path.join(STATIC_DIR, 'static'), 'guide.html')

@pages_bp.route('/guide/pipeline')
def serve_guide_pipeline():
    """Guide Pipeline — le même contenu que GUIDE-PIPELINE.md (racine), rendu en
    HTML via markdown2 (module déjà installé), avec une coquille style guide.html.
    C'est le contrat de travail des agents IA pour la chaîne scraping →
    enrichissement → récap d'activité → rédaction email/séquences → envoi."""
    try:
        import markdown2
    except ImportError:
        return jsonify({"error": "module markdown2 manquant (pip install markdown2)"}), 500
    root = os.path.dirname(STATIC_DIR)  # au-dessus de dashboard/ → racine du dépôt
    md_path = os.path.join(root, 'GUIDE-PIPELINE.md')
    if not os.path.exists(md_path):
        return jsonify({"error": "GUIDE-PIPELINE.md introuvable", "path": md_path}), 404
    with open(md_path, encoding='utf-8') as f:
        html_body = markdown2.markdown(f.read(), extras=['tables', 'fenced-code-blocks', 'toc', 'header-ids'])
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initismal-scale=1">
<title>Guide Pipeline — Prospection Machine</title>
<link rel="stylesheet" href="/static/css/guide.css">
<style>
  body {{ background:#0f172a;color:#e2e8f0;font-family:Inter,system-ui,sans-serif;line-height:1.65;padding:32px 20px 80px; }}
  .wrap {{ max-width:900px;margin:0 auto; }}
  h1,h2,h3 {{ color:#f8fafc; }}
  h1 {{ border-bottom:2px solid #6366f1;padding-bottom:8px; }}
  h2 {{ border-bottom:1px solid #334155;padding-bottom:6px;margin-top:36px; }}
  code {{ background:#1e293b;padding:2px 6px;border-radius:4px;color:#a5b4fc;font-size:.9em; }}
  pre {{ background:#0b1220;border:1px solid #1e293b;border-radius:10px;padding:16px;overflow-x:auto; }}
  pre code {{ background:none;padding:0;color:#cbd5e1; }}
  table {{ border-collapse:collapse;width:100%;margin:16px 0; }}
  th,td {{ border:1px solid #334155;padding:8px 12px;text-align:left;font-size:.92em; }}
  th {{ background:#1e293b;color:#f8fafc; }}
  blockquote {{ border-left:4px solid #6366f1;margin-left:0;padding:8px 16px;background:#172033;color:#cbd5e1; }}
  a {{ color:#818cf8; }}
</style>
</head>
<body>
<div class="wrap">
<p style="font-size:.85em;color:#94a3b8">← <a href="/guide">Retour au guide dashboard</a></p>
{html_body}
</div>
</body>
</html>"""

@pages_bp.route('/sw.js')
def serve_sw():
    return send_from_directory(STATIC_DIR, 'sw.js')

@pages_bp.route('/manifest.json')
def serve_manifest():
    return send_from_directory(STATIC_DIR, 'manifest.json')

@pages_bp.route('/api/config')
def api_config():
    return jsonify({
        'resend_configured': bool(os.getenv('RESEND_API_KEY')),
        'brevo_configured': bool(os.getenv('BREVO_API_KEY')),
        'groq_configured': bool(os.getenv('GROQ_API_KEY')),
        'provider_name': 'Resend' if os.getenv('RESEND_API_KEY') else 'None'
    })

@pages_bp.route('/api/sync', methods=['POST'])
def api_sync():
    """Déclenche la synchronisation SQLite → Google Sheets."""
    try:
        from database.sheets_sync import sync_to_sheets
        result = sync_to_sheets()
        return jsonify({"success": True, **(result if isinstance(result, dict) else {})})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@pages_bp.route('/api/settings/identity', methods=['POST'])
def api_settings_identity():
    try:
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        email = data.get('email', '').strip()
        if not name or not email:
            return jsonify({'error': 'Nom et Email requis'}), 400
        
        from core.config import set_env_var
        set_env_var('BREVO_SENDER_NAME', name)
        set_env_var('BREVO_SENDER_EMAIL', email)
        
        return jsonify({'success': True, 'message': 'Identité sauvegardée'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
