# -*- coding: utf-8 -*-
"""
dashboard/routes/objectifs.py — ALIAS TEMPORAIRE (code 301, moved permanently).

Les anciens endpoints /api/v2/objectifs* ont été remplacés par le modèle
Campagne → Liste (voir dashboard/routes/campagnes.py et dashboard/routes/listes.py).
Ce blueprint ne fait que rediriger vers les nouvelles routes pour ne pas casser
les anciens clients, scripts et bookmarks le temps de la bascule.
"""
from flask import Blueprint, redirect, request, url_for

objectifs_bp = Blueprint('objectifs_bp', __name__)


def _redirect(target, preserve_query=False):
    if preserve_query and request.query_string:
        target = f"{target}?{request.query_string.decode('utf-8')}"
    return redirect(target, code=301)


@objectifs_bp.route('/api/v2/objectifs/<int:objectif_id>/send', methods=['POST'])
def compat_send_now(objectif_id):
    return _redirect(url_for('campagnes_bp.api_send_campagne_now', campagne_id=objectif_id))


@objectifs_bp.route('/api/v2/objectifs/<int:objectif_id>/sequence', methods=['GET'])
def compat_sequence_get(objectif_id):
    return _redirect(url_for('campagnes_bp.api_campagne_sequence', campagne_id=objectif_id))


@objectifs_bp.route('/api/v2/objectifs/<int:objectif_id>/sequence', methods=['POST'])
def compat_sequence_post(objectif_id):
    return _redirect(url_for('campagnes_bp.api_campagne_sequence_add', campagne_id=objectif_id))


@objectifs_bp.route('/api/v2/objectifs', methods=['GET'])
def compat_list():
    return _redirect(url_for('campagnes_bp.api_list_campagnes'), preserve_query=True)


@objectifs_bp.route('/api/v2/objectifs', methods=['POST'])
def compat_create():
    return _redirect(url_for('campagnes_bp.api_create_campagne'))


@objectifs_bp.route('/api/v2/objectifs/<int:objectif_id>', methods=['PUT'])
def compat_update(objectif_id):
    return _redirect(url_for('campagnes_bp.api_update_campagne', campagne_id=objectif_id))


@objectifs_bp.route('/api/v2/objectifs/<int:objectif_id>', methods=['DELETE'])
def compat_delete(objectif_id):
    return _redirect(url_for('campagnes_bp.api_delete_campagne', campagne_id=objectif_id))


@objectifs_bp.route('/api/v2/objectifs/<int:objectif_id>/stats', methods=['GET'])
def compat_stats(objectif_id):
    return _redirect(url_for('campagnes_bp.api_campagne_stats', campagne_id=objectif_id))


@objectifs_bp.route('/api/v2/objectifs/<int:objectif_id>/leads', methods=['GET'])
def compat_leads_get(objectif_id):
    return _redirect(url_for('campagnes_bp.api_list_prospects', campagne_id=objectif_id), preserve_query=True)


@objectifs_bp.route('/api/v2/objectifs/<int:objectif_id>/leads', methods=['POST'])
def compat_leads_post(objectif_id):
    return _redirect(url_for('campagnes_bp.api_create_prospect', campagne_id=objectif_id))


@objectifs_bp.route('/api/v2/objectifs/<int:objectif_id>/leads/import', methods=['POST'])
def compat_leads_import(objectif_id):
    return _redirect(url_for('campagnes_bp.api_import_prospects', campagne_id=objectif_id))