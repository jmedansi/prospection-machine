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
    return render_template('views/dashboard_v5.html')

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
