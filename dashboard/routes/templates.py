# -*- coding: utf-8 -*-
"""
dashboard/routes/templates.py
API pour la gestion des templates email (lecture / écriture / preview)
"""
import os
from flask import Blueprint, jsonify, request, send_file

templates_bp = Blueprint('templates', __name__, url_prefix='/api/templates')

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATES_DIR = os.path.join(ROOT, 'templates')
EMAIL_DIR = os.path.join(TEMPLATES_DIR, 'emails')
SNIPER_DIR = os.path.join(ROOT, 'sniper', 'templates')

TEMPLATE_CATEGORIES = {
    'pipeline': {
        'label': 'Pipeline principal',
        'dir': EMAIL_DIR,
        'files': [
            'template_profil_a.html',
            'template_profil_b.html',
            'template_profil_c.html',
            'template_profil_d.html',
            'email_step2_maps.html',
        ],
    },
    'sniper': {
        'label': 'Sniper B2B',
        'dir': SNIPER_DIR,
        'files': None,
    },
}


def _list_sniper_templates():
    if not os.path.exists(SNIPER_DIR):
        return []
    return sorted([f for f in os.listdir(SNIPER_DIR) if f.startswith('email_') and f.endswith('.html')])


def _template_path(category, filename):
    if category == 'sniper':
        return os.path.join(SNIPER_DIR, filename)
    elif category == 'pipeline':
        return os.path.join(EMAIL_DIR, filename)
    return None


@templates_bp.route('/')
def list_templates():
    sniper_files = _list_sniper_templates()
    return jsonify({
        'categories': [
            {
                'id': 'pipeline',
                'label': 'Pipeline principal',
                'files': [
                    {
                        'name': f,
                        'label': f.replace('template_profil_', 'Profil ').replace('.html', '').replace('_', ' ').title(),
                        'path': f'templates/emails/{f}',
                    }
                    for f in TEMPLATE_CATEGORIES['pipeline']['files']
                ],
            },
            {
                'id': 'sniper',
                'label': 'Sniper B2B',
                'files': [
                    {
                        'name': f,
                        'label': f.replace('email_', '').replace('_', ' ').replace('.html', '').title(),
                        'path': f'sniper/templates/{f}',
                    }
                    for f in sniper_files
                ],
            },
        ],
        'variables': {
            'pipeline': [
                {'var': '{{NOM}}', 'desc': "Nom de l'entreprise"},
                {'var': '{{SITE}}', 'desc': "URL du site web"},
                {'var': '{{SCORE}}', 'desc': "Score mobile (0-100)"},
                {'var': '{{LCP}}', 'desc': "Temps de chargement (secondes)"},
                {'var': '{{RATING}}', 'desc': "Note Google (ex: 3.8)"},
                {'var': '{{REVIEWS}}', 'desc': "Nombre d'avis Google"},
                {'var': '{{SECTEUR}}', 'desc': "Secteur d'activité"},
                {'var': '{{VILLE}}', 'desc': "Ville"},
            ],
            'sniper': [
                {'var': '{{NOM}}', 'desc': "Nom de l'entreprise"},
                {'var': '{{SITE}}', 'desc': "URL du site web"},
                {'var': '{{SCORE}}', 'desc': "Score mobile (0-100)"},
                {'var': '{{LCP}}', 'desc': "Temps de chargement (secondes)"},
                {'var': '{{CMS}}', 'desc': "CMS détecté"},
                {'var': '{{SERVER}}', 'desc': "Serveur / infrastructure"},
                {'var': '{{LIEN_RAPPORT}}', 'desc': "URL du rapport d'audit"},
                {'var': '{{ENTREPRISE}}', 'desc': "Nom de l'entreprise (alt)"},
            ],
        },
    })


@templates_bp.route('/<category>/<path:filename>')
def get_template(category, filename):
    path = _template_path(category, filename)
    if not path or not os.path.exists(path):
        return jsonify({'error': 'Template non trouvé'}), 404
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    return jsonify({'name': filename, 'category': category, 'content': content})


@templates_bp.route('/<category>/<path:filename>', methods=['POST'])
def save_template(category, filename):
    path = _template_path(category, filename)
    if not path:
        return jsonify({'error': 'Catégorie invalide'}), 400
    if not os.path.exists(path):
        return jsonify({'error': 'Template non trouvé'}), 404
    data = request.get_json() or {}
    content = data.get('content', '')
    if content is None:
        return jsonify({'error': 'Contenu requis'}), 400
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return jsonify({'success': True, 'message': f'{filename} sauvegardé'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@templates_bp.route('/<category>/<path:filename>/preview')
def preview_template(category, filename):
    path = _template_path(category, filename)
    if not path or not os.path.exists(path):
        return jsonify({'error': 'Template non trouvé'}), 404
    return send_file(path, mimetype='text/html')


@templates_bp.route('/debug/email-mapping', methods=['GET'])
def debug_email_mapping():
    """
    Teste le mapping complet : situation → profil → template email.
    Affiche tous les 8 scénarios avec profils et titres générés.
    """
    import re
    from copywriter.main import generate_email_content
    from dashboard.pipeline.email_generation import SITUATION_TO_PROFILE
    from envoi.email_builder import build_premium_email

    def make_audit_for_label(label: str) -> dict:
        base = {
            'nom': 'Test Entreprise',
            'site_web': 'https://example.com',
            'ville': 'Paris',
            'category': 'Restaurant',
            'mobile_score': 85,
            'desktop_score': 95,
            'lcp_ms': 1800,
            'fcp_ms': 900,
            'cls': 0.05,
            'has_https': True,
            'has_meta_description': True,
            'h1_count': 1,
            'render_blocking_scripts': 0,
            'uses_cache': True,
            'tel_link': True,
            'has_contact_button': True,
            'images_without_alt': 0,
            'has_analytics': True,
            'cms_detected': 'WordPress',
            'rating': 4.6,
            'reviews_count': 120,
        }
        if label == 'Pas de site web':
            base.update({'site_web': '', 'has_meta_description': False, 'cms_detected': '', 'rating': 0, 'reviews_count': 0})
        elif label == 'Site lent sur mobile':
            base.update({'lcp_ms': 4200, 'mobile_score': 45, 'rating': 4.0, 'reviews_count': 25})
        elif label == 'Bon GMB, mauvais site':
            base.update({'lcp_ms': 4200, 'mobile_score': 45, 'rating': 4.5, 'reviews_count': 70})
        elif label == 'Pas de meta description':
            base.update({'has_meta_description': False, 'rating': 4.4, 'reviews_count': 55})
        elif label == "Peu d'avis Google":
            base.update({'rating': 4.3, 'reviews_count': 8})
        elif label == 'Note Google faible':
            base.update({'rating': 3.6, 'reviews_count': 55})
        elif label == 'Pas de bouton contact / tel':
            base.update({'has_contact_button': False, 'tel_link': False})
        elif label == 'CMS vieillot (Wix/Jimdo)':
            base.update({'cms_detected': 'Wix'})
        return base

    results = []
    main_problem = {'service_propose': 'Test', 'probleme_principal': 'Test'}

    for situation, profile in SITUATION_TO_PROFILE.items():
        try:
            audit_dict = make_audit_for_label(situation)
            copy_result = generate_email_content(audit_dict, main_problem)
            detected_situation = copy_result.get('phrase_synthese', 'N/A')

            builder_data = {
                **audit_dict,
                'profile': profile,
                'template_variant': 'v1',
                'lien_rapport': 'https://audit.incidenx.com/test-slug/',
            }
            html = build_premium_email(builder_data, verify_link=False)

            title_match = re.search(r'<title>([^<]+)</title>', html) if html else None
            title = title_match.group(1) if title_match else 'N/A'

            status = 'OK' if detected_situation == situation and html else 'ERREUR'

            results.append({
                'situation': situation,
                'detected': detected_situation,
                'profile': profile,
                'title': title,
                'status': status,
            })
        except Exception as e:
            results.append({
                'situation': situation,
                'detected': 'ERREUR',
                'profile': profile,
                'title': f'Exception: {str(e)[:100]}',
                'status': 'ERREUR',
            })

    return jsonify({
        'timestamp': os.popen('date').read().strip() if os.name == 'posix' else '',
        'total': len(results),
        'passed': sum(1 for r in results if r['status'] == 'OK'),
        'failed': sum(1 for r in results if r['status'] == 'ERREUR'),
        'mapping': results,
    })