# -*- coding: utf-8 -*-
import os
import csv
import io
from flask import Blueprint, jsonify, request, make_response
from database import (
    get_conn, get_dashboard_stats, get_niche_performance, get_ab_test_performance,
)

stats_bp = Blueprint('stats', __name__)

@stats_bp.route('/api/stats')
def api_stats():
    try:
        campaign_id = request.args.get('campaign_id', type=int)
        campaign_ids = request.args.get('campaign_ids')
        date_start = request.args.get('date_start')
        date_end = request.args.get('date_end')
        version = request.args.get('v')

        stats = get_dashboard_stats(
            campaign_id=campaign_id,
            date_start=date_start,
            date_end=date_end,
            campaign_ids=campaign_ids
        )

        if version == '5':
            # Mapping à plat en anglais pour la V5
            return jsonify({
                'scraped': stats.get('leads_scrapes', 0),
                'audited': stats.get('leads_audites', 0),
                'ready_emails': stats.get('emails_prets', 0),
                'sent': stats.get('envoyes', 0),
                'avg_score': stats.get('score_moyen', 0),
                'avg_mobile': stats.get('mobile_moyen', 0),
                'avg_seo': stats.get('seo_moyen', 0),
                'opens': stats.get('emails_ouverts', 0),
                'replies': stats.get('emails_repondus', 0),
                'meetings': stats.get('rdv_obtenus', 0),
                'open_rate': stats.get('taux_ouverture', 0),
                'reply_rate': stats.get('taux_reponse', 0),
                'meeting_rate': stats.get('taux_rdv', 0),
                'bounces': stats.get('bounces', 0),
                'spam': stats.get('spam', 0)
            })

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
            **stats
        }
        return jsonify(response)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@stats_bp.route('/api/stats/funnel')
def api_stats_funnel():
    try:
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
        return jsonify({'error': str(e)}), 500

@stats_bp.route('/api/stats/niche')
@stats_bp.route('/api/stats/niches')
def api_stats_niche():
    try:
        niches = get_niche_performance()
        return jsonify([dict(n) for n in niches])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@stats_bp.route('/api/stats/export')
def api_stats_export():
    try:
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
        return str(e), 500

@stats_bp.route('/api/stats/ab_test')
def api_stats_ab_test():
    try:
        results = get_ab_test_performance()
        return jsonify([dict(r) for r in results])
    except Exception as e:
        return jsonify({'error': str(e)}), 500
