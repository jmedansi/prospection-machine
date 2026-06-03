# -*- coding: utf-8 -*-
"""
dashboard/routes/review.py
Route pour la revue manuelle des leads avant envoi.
"""
from flask import Blueprint, request
from database import get_conn
from markupsafe import escape

review_bp = Blueprint('review', __name__)

@review_bp.route("/review")
def pipeline_review():
    ids_param = request.args.get("ids", "")
    try:
        lead_ids = [int(x) for x in ids_param.split(",") if x.strip().isdigit()]
    except: lead_ids = []
    if not lead_ids: return "<h2>Aucun lead à réviser.</h2>", 400

    leads = []
    with get_conn() as conn:
        for lid in lead_ids:
            row = conn.execute("""
                SELECT lb.id, lb.nom, lb.email, lb.site_web, lb.rating, lb.nb_avis,
                       la.probleme_principal, la.score_urgence,
                       la.email_objet, la.email_corps, la.lien_rapport
                FROM leads_bruts lb
                JOIN leads_audites la ON lb.id = la.lead_id
                WHERE lb.id = ?
            """, (lid,)).fetchone()
            if row:
                d = dict(row)
                lien = d.get('lien_rapport') or ''
                if lien.startswith('local://'):
                    slug = lien.replace('local://', '').strip('/')
                    d['preview_url'] = f'/previews/{slug}/'
                else: d['preview_url'] = lien or None
                leads.append(d)

    rows_html = ""
    for i, l in enumerate(leads, 1):
        rapport_btn = f'<a href="{escape(l["preview_url"])}" target="_blank" class="btn-rapport">Voir rapport</a>' if l["preview_url"] else ""
        rows_html += f"""
        <div class="lead-card">
          <div class="lead-header">
            <strong>{i}. {escape(l['nom'])}</strong> ({escape(l['email'] or '—')})
            {rapport_btn}
          </div>
          <div class="lead-problem">{escape(l['probleme_principal'] or 'Non défini')}</div>
          <details><summary>Mail</summary><pre>{escape(l['email_corps'] or '')}</pre></details>
        </div>"""
    
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Review</title>
    <style>
        body{{background:#0c2832;color:#d0e8ec;padding:20px;font-family:sans-serif}}
        .lead-card{{background:#0f3040;padding:15px;margin-bottom:10px;border-radius:8px;border:1px solid #1a4a5a}}
        .btn-rapport{{background:#7ad4e8;color:#0c2832;margin-left:20px;text-decoration:none;padding:2px 8px;border-radius:4px;font-size:12px}}
        details{{margin-top:10px;cursor:pointer}}
        pre{{background:#081b22;padding:10px;white-space:pre-wrap;font-size:13px;border-radius:4px}}
    </style></head>
    <body><h1>Review Pipeline</h1>{rows_html}</body></html>"""
