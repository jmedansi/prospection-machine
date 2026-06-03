# -*- coding: utf-8 -*-
"""
dashboard/routes/rapports.py — Routes API rapports / previews

P0 fix #4 :
  - GET  /api/previews         (liste les rapports locaux)
  - POST /api/previews/push    (publie vers GitHub Pages)
  - GET  /previews/<slug>/     (sert les fichiers statiques locaux)
"""
import os
from flask import Blueprint, jsonify, request, send_from_directory, abort
from agents.publieur import publieur_agent

rapports_bp = Blueprint("rapports", __name__)

ROOT        = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPORTS_DIR = os.path.join(ROOT, "reporter", "reports")


@rapports_bp.route("/api/previews")
def api_previews_list():
    """Liste tous les rapports disponibles localement."""
    try:
        rapports = publieur_agent.list_local()
        return jsonify({"rapports": rapports, "count": len(rapports)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@rapports_bp.route("/api/previews/push", methods=["POST"])
def api_previews_push():
    """Publie un ou plusieurs rapports locaux vers GitHub Pages."""
    data  = request.get_json() or {}
    slugs = data.get("slugs", [])
    if not slugs:
        return jsonify({"error": "slugs requis (liste de noms de dossiers)"}), 400

    result = publieur_agent.run(slugs=slugs)
    if not result:
        err = getattr(result, "error", "Erreur publication")
        det = getattr(result, "data", {})
        return jsonify({"error": err, "details": det}), 500
    return jsonify({"success": True, **result.data})


@rapports_bp.route("/api/rapports", methods=["GET"])
def api_rapports_alias():
    """Alias de /api/previews pour compatibilité frontend."""
    try:
        rapports = publieur_agent.list_local()
        return jsonify({"rapports": rapports, "count": len(rapports)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@rapports_bp.route("/previews/<slug>/")
@rapports_bp.route("/previews/<slug>/<path:filename>")
def serve_preview(slug, filename="index.html"):
    """Sert les fichiers statiques d'un rapport local."""
    slug_dir = os.path.join(REPORTS_DIR, slug)
    if not os.path.isdir(slug_dir):
        abort(404)
    return send_from_directory(slug_dir, filename)
