# -*- coding: utf-8 -*-
"""
dashboard/app.py — Serveur Flask du cockpit Incidenx (Modularisé)
"""
import os
import sys
from flask import Flask
from flask_socketio import SocketIO

# --- Configuration et Logging ---
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT)

from core.config import ensure_env
ensure_env()
from config_manager import logger

# --- Database ---
from database import init_db
from database.schema import migrate_db
init_db()
migrate_db()

# --- Cleanup on Startup ---
try:
    from services.campaign_tracker import reset_all_active_campaigns
    count = reset_all_active_campaigns(reason="Redémarrage serveur")
    if count > 0:
        logger.info(f"  [CLEANUP] {count} campagnes orphelines marquées comme 'stopped'")
except Exception as e:
    logger.error(f"  [CLEANUP] Erreur reset campagnes: {e}")

# --- SocketIO global ---
socketio = SocketIO(cors_allowed_origins="*", async_mode='threading')

def create_app():
    """App Factory as specified in the master plan (3.3)."""
    app = Flask(__name__, 
                static_folder=os.path.join(ROOT, 'dashboard', 'static'), 
                static_url_path='/static')
    
    # Init SocketIO with app
    socketio.init_app(app)
    
    # SocketIO events
    @socketio.on('connect')
    def handle_connect():
        logger.info("Client WebSocket connecté")
    
    @socketio.on('disconnect')
    def handle_disconnect():
        logger.info("Client WebSocket déconnecté")
    
    # Configuration CORS
    @app.after_request
    def add_cors_headers(response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return response

    # Registration of Blueprints (Phase 3.1)
    from dashboard.routes import (
        leads_bp, audits_bp, emails_bp, campaigns_bp,
        stats_bp, review_bp, pages_bp, rapports_bp, health_bp,
        sniper_bp, deploy_bp, templates_bp, webhooks_bp
    )

    app.register_blueprint(leads_bp)
    app.register_blueprint(audits_bp)
    app.register_blueprint(emails_bp)
    app.register_blueprint(campaigns_bp)
    app.register_blueprint(stats_bp)
    app.register_blueprint(review_bp)
    app.register_blueprint(pages_bp)
    app.register_blueprint(rapports_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(sniper_bp)
    app.register_blueprint(deploy_bp)
    app.register_blueprint(templates_bp)
    app.register_blueprint(webhooks_bp)
    
    # Discovery of child modules (Phase 4.2)
    def _discover_modules():
        modules_dir = os.path.join(ROOT, 'modules')
        if not os.path.exists(modules_dir): return
        import importlib
        for item in os.listdir(modules_dir):
            item_path = os.path.join(modules_dir, item)
            if os.path.isdir(item_path) and os.path.exists(os.path.join(item_path, '__init__.py')):
                try:
                    importlib.import_module(f'modules.{item}')
                    logger.info(f"  [MODULE] {item} chargé avec succès")
                except Exception as e:
                    logger.error(f"  [MODULE] Erreur chargement {item}: {e}")
    
    _discover_modules()
    
    return app

if __name__ == '__main__':
    print("\n" + "="*55)
    print("  Incidenx Cockpit - http://localhost:5001")
    print("  Status: Modularized (Blueprints + Services)")
    print("="*55 + "\n")
    
    app = create_app()
    
    # Scheduler
    try:
        from dashboard.scheduler import init_scheduler
        init_scheduler(app)
        print("  [Scheduler] Planificateur démarré")
    except Exception as e:
        print(f"  [Scheduler] Non démarré : {e}")

    # Audit Worker background thread
    try:
        import threading
        from audit_worker import run_loop
        threading.Thread(target=run_loop, daemon=True, name="AuditWorker").start()
        print("  [AuditWorker] Thread de traitement d'audit démarré")
    except Exception as e:
        print(f"  [AuditWorker] Non démarré : {e}")

    # Lancement Flask avec SocketIO (port 5001)
    socketio.run(app, host='127.0.0.1', port=5001, debug=False, allow_unsafe_werkzeug=True)
