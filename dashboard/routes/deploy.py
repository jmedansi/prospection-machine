# -*- coding: utf-8 -*-
"""
dashboard/routes/deploy.py — Route API pour déployer des ressources CTA.
"""
from flask import Blueprint, jsonify, request
from deploy_resource import deploy_resource

deploy_bp = Blueprint('deploy', __name__)


@deploy_bp.route('/api/deploy-resource', methods=['POST'])
def deploy_resource_endpoint():
    """
    Déploie une ressource CTA sur GitHub Pages.
    
    Body JSON:
    {
        "slug": "guide-facebook-monetisation-2025",
        "title": "Guide complet : Monétiser Facebook en 47 jours",
        "content": "# Introduction\n\nLe contenu complet ici...",
        "theme": "default"  // optionnel
    }
    
    Returns:
    {
        "success": true,
        "url": "https://audit.incidenx.com/guide-facebook-monetisation-2025/",
        "slug": "guide-facebook-monetisation-2025"
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Missing JSON body"}), 400
    
    slug = data.get("slug")
    title = data.get("title")
    content = data.get("content")
    theme = data.get("theme", "default")
    
    if not slug or not title or not content:
        return jsonify({"success": False, "error": "Missing required fields: slug, title, content"}), 400
    
    result = deploy_resource(slug=slug, title=title, content=content, theme=theme)
    
    if result.get("success"):
        return jsonify(result), 200
    else:
        return jsonify(result), 500