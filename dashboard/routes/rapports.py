# -*- coding: utf-8 -*-
"""
dashboard/routes/rapports.py — Routes API rapports / previews

  - GET  /api/previews         (liste les rapports locaux, enrichis avec données DB)
  - POST /api/previews/push    (publie vers GitHub Pages)
  - GET  /api/rapports         (alias de /api/previews pour compat. frontend)
  - GET  /previews/<slug>/     (sert les fichiers statiques locaux)
"""
import logging
import os
from flask import Blueprint, jsonify, request, send_from_directory, abort
from agents.publieur import publieur_agent

rapports_bp = Blueprint("rapports", __name__)
logger      = logging.getLogger("routes.rapports")

ROOT        = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPORTS_DIR = os.path.join(ROOT, "reporter", "reports")


def _enrich_local_reports(rapports: list) -> list:
    """
    Enrichit les rapports locaux avec les métadonnées DB (nom, secteur, score, id).
    Permet à la table frontend d'afficher des infos lisibles au lieu des slugs.
    """
    try:
        from database.connection import get_conn
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT lb.id, lb.nom, lb.secteur,
                       la.lien_rapport, la.score_urgence, la.date_audit
                FROM leads_audites la
                JOIN leads_bruts lb ON lb.id = la.lead_id
                WHERE la.lien_rapport IS NOT NULL
            """).fetchall()

        # Construit un map slug → données DB
        db_map = {}
        for row in rows:
            lien = row["lien_rapport"] or ""
            slug = (lien
                    .replace("local://", "")
                    .replace("https://audit.incidenx.com/", "")
                    .strip("/"))
            db_map[slug] = dict(row)

        enriched = []
        for r in rapports:
            db = db_map.get(r["slug"], {})
            enriched.append({
                **r,
                "id":           db.get("id"),
                "nom":          db.get("nom", r["slug"]),
                "secteur":      db.get("secteur", "—"),
                "score_urgence": db.get("score_urgence", 0),
                "date_audit":   db.get("date_audit", ""),
                "lien_rapport": db.get("lien_rapport", f"local://{r['slug']}/"),
            })
        return enriched

    except Exception as e:
        logger.warning(f"_enrich_local_reports: {e}")
        return rapports


@rapports_bp.route("/api/previews")
def api_previews_list():
    """Liste tous les rapports disponibles localement avec données DB enrichies."""
    try:
        rapports = publieur_agent.list_local()
        rapports = _enrich_local_reports(rapports)
        return jsonify({"rapports": rapports, "previews": rapports, "count": len(rapports)})
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

    # Normalise au format attendu par le frontend :
    # { results: [{slug, status, url?, message?}] }
    published = result.data.get("published", []) if result.data else []
    failed    = result.data.get("failed",    []) if result.data else []

    results = []
    for p in published:
        results.append({"slug": p["slug"], "status": "published", "url": p.get("url", "")})
    for f in failed:
        results.append({"slug": f["slug"], "status": "error",     "message": f.get("error", "")})

    if not result:
        return jsonify({"error": result.error or "Erreur publication", "results": results}), 500

    return jsonify({"success": True, "results": results})


@rapports_bp.route("/api/rapports", methods=["GET"])
def api_rapports_alias():
    """Alias de /api/previews pour compatibilité frontend."""
    return api_previews_list()


@rapports_bp.route("/previews/<slug>/")
@rapports_bp.route("/previews/<slug>/<path:filename>")
def serve_preview(slug, filename="index.html"):
    """Sert les fichiers statiques d'un rapport local."""
    slug_dir = os.path.join(REPORTS_DIR, slug)
    if not os.path.isdir(slug_dir):
        abort(404)
    return send_from_directory(slug_dir, filename)
