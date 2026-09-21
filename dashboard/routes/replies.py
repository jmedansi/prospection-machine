# -*- coding: utf-8 -*-
"""
dashboard/routes/replies.py — API v2 des réponses entrantes (IMAP).

  POST /api/v2/replies/poll      → déclenche un poll manuel (résumé par boîte)
  GET  /api/v2/replies/recent    → derniers événements réponses/NDR/auto_reply

Coté métier : `envoi/reply_poller.py` (transition → a_traiter_humain).
"""
from flask import Blueprint, jsonify, request

from database.connection import get_conn

replies_bp = Blueprint('replies_bp', __name__)


@replies_bp.route('/api/v2/replies/poll', methods=['POST'])
def api_replies_poll():
    from envoi.reply_poller import run_poll
    data = request.get_json(silent=True) or {}
    try:
        lookback = int(data.get('lookback_hours') or 48)
    except (TypeError, ValueError):
        lookback = 48
    res = run_poll(lookback_hours=lookback)
    return jsonify(res)


@replies_bp.route('/api/v2/replies/recent', methods=['GET'])
def api_replies_recent():
    limit = min(int(request.args.get('limit') or 25), 100)
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT ev.id, ev.prospect_id, ev.campagne_id, ev.event_type,
                      ev.payload, ev.created_at,
                      p.nom AS prospect_nom, p.email AS prospect_email,
                      c.nom AS campagne_nom, c.nom AS objectif_nom
               FROM prospect_events ev
               LEFT JOIN prospects p ON p.id = ev.prospect_id
               LEFT JOIN campagnes c ON c.id = ev.campagne_id
               WHERE ev.event_type IN ('reponse', 'ndr', 'auto_reply')
               ORDER BY ev.id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    events = []
    for r in rows:
        ev = dict(r)
        import json
        try:
            ev['payload'] = json.loads(ev['payload'] or '{}')
        except Exception:
            ev['payload'] = {}
        events.append(ev)
    return jsonify({'success': True, 'events': events})


@replies_bp.route('/api/v2/suivi/echanges', methods=['GET'])
def api_suivi_echanges():
    """Historique des échanges de l'onglet « Suivi » V6.

    Journal complet des `prospect_events` (initial, relance_k, reponse, ndr,
    auto_reply, validation_requete, desinscription, creation, import, status_change).
    `campagne_id` présent → filtre sur la campagne active ; absent → toutes campagnes.
    """
    campagne_id = request.args.get('campagne_id', type=int)
    limit = min(int(request.args.get('limit') or 200), 1000)
    where = "WHERE 1=1"
    params = []
    if campagne_id:
        where += " AND ev.campagne_id = ?"
        params.append(campagne_id)
    with get_conn() as conn:
        rows = conn.execute(
            f"""SELECT ev.id, ev.prospect_id, ev.campagne_id, ev.event_type,
                       ev.payload, ev.created_at,
                       p.nom AS prospect_nom, p.prenom, p.email AS prospect_email,
                       c.nom AS campagne_nom
                FROM prospect_events ev
                LEFT JOIN prospects p ON p.id = ev.prospect_id
                LEFT JOIN campagnes c ON c.id = ev.campagne_id
                {where}
                ORDER BY ev.id DESC LIMIT ?""",
            params + [limit],
        ).fetchall()
    events = []
    for r in rows:
        ev = dict(r)
        import json
        try:
            ev['payload'] = json.loads(ev['payload'] or '{}')
        except Exception:
            ev['payload'] = {}
        events.append(ev)
    return jsonify({'success': True, 'events': events})