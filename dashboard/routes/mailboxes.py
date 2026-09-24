# -*- coding: utf-8 -*-
"""
dashboard/routes/mailboxes.py — API boîtes d'expédition (table `mailboxes`)

- GET  /api/mailboxes                 : liste les boîtes (label, email, backend,
                                        actif, quota_jour, usage_jour, campagne_pool)
- PUT  /api/mailboxes/<int:id>        : mise à jour partielle (quota_jour, actif, label)
- POST /api/mailboxes/<int:id>/reset  : remet usage_jour à 0 immédiatement
- GET  /api/settings/envoi-backend    : backend global (smtp/resend/auto) + éligibilité
- POST /api/settings/envoi-backend    : persiste le backend global
"""
from flask import Blueprint, jsonify, request

from database.connection import get_conn

from envoi.gateway import get_global_backend, set_global_backend

mailboxes_bp = Blueprint('mailboxes_bp', __name__)


def _row(m):
    return {
        'id': m['id'],
        'label': m.get('label') or '',
        'email': m.get('email') or '',
        'backend': m.get('backend') or 'smtp',
        'actif': bool(m.get('actif')),
        'quota_jour': m.get('quota_jour') or 0,
        'usage_jour': m.get('usage_jour') or 0,
        'campagne_pool': m.get('campagne_pool') or '*',
        'last_send_at': m.get('last_send_at'),
    }


@mailboxes_bp.route('/api/mailboxes', methods=['GET'])
def api_list_mailboxes():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM mailboxes ORDER BY id").fetchall()
    return jsonify({'success': True, 'boites': [_row(dict(r)) for r in rows]})


@mailboxes_bp.route('/api/mailboxes/<int:mid>', methods=['PUT'])
def api_update_mailbox(mid):
    data = request.get_json(silent=True) or {}
    sets, params = [], []
    if 'quota_jour' in data:
        try:
            quota = max(0, int(data.get('quota_jour')))
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'quota_jour doit être un nombre'}), 400
        sets.append("quota_jour = ?")
        params.append(quota)
    if 'actif' in data:
        sets.append("actif = ?")
        params.append(1 if data.get('actif') else 0)
    if 'label' in data:
        sets.append("label = ?")
        params.append(str(data.get('label') or ''))
    if not sets:
        return jsonify({'success': False, 'error': 'aucun champ à mettre à jour'}), 400
    with get_conn() as conn:
        cur = conn.execute("UPDATE mailboxes SET %s WHERE id = ?" % ', '.join(sets), params + [mid])
        conn.commit()
    if cur.rowcount == 0:
        return jsonify({'success': False, 'error': 'boîte introuvable'}), 404
    return jsonify({'success': True})


@mailboxes_bp.route('/api/mailboxes/<int:mid>/reset', methods=['POST'])
def api_reset_mailbox_usage(mid):
    with get_conn() as conn:
        cur = conn.execute("UPDATE mailboxes SET usage_jour = 0 WHERE id = ?", (mid,))
        conn.commit()
    if cur.rowcount == 0:
        return jsonify({'success': False, 'error': 'boîte introuvable'}), 404
    return jsonify({'success': True})


@mailboxes_bp.route('/api/settings/envoi-backend', methods=['GET'])
def api_get_envoi_backend():
    """Backend d'envoi global choisi dans Paramètres (défaut : auto)."""
    backend = get_global_backend()
    with get_conn() as conn:
        rows = conn.execute("SELECT backend, COUNT(*) n FROM mailboxes GROUP BY backend").fetchall()
    disponibles = {r['backend']: r['n'] for r in rows}
    return jsonify({
        'success': True,
        'backend': backend,
        'options': ['auto', 'smtp', 'resend'],
        'disponibles': disponibles,
        'interprete': 'auto' if backend == 'auto' else backend,
    })


@mailboxes_bp.route('/api/settings/envoi-backend', methods=['POST'])
def api_set_envoi_backend():
    data = request.get_json(silent=True) or {}
    value = str(data.get('backend') or 'auto').strip().lower()
    if value not in ('auto', 'smtp', 'resend'):
        return jsonify({'success': False, 'error': "backend doit être 'auto', 'smtp' ou 'resend'"}), 400
    set_global_backend(value)
    return jsonify({'success': True, 'backend': value})