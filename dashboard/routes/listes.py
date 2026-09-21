# -*- coding: utf-8 -*-
"""
dashboard/routes/listes.py — API v2 des listes.

Une liste est l'unité opérationnelle d'une campagne (1 scraping / 1 import / 1 secteur)
et porte directement les prospects (`prospects.liste_id`).
"""
import csv
import io
import json

from flask import Blueprint, jsonify, request

from database import listes as listes_repo
from database import prospects as prospects_repo
from core.state_machine import statut_display

listes_bp = Blueprint('listes_bp', __name__)

VALID_LEAD_FIELDS = {
    'nom', 'prenom', 'email', 'telephone', 'entreprise', 'site_web', 'adresse',
    'ville', 'secteur', 'rating', 'nb_avis', 'source', 'score',
}


def _json_or_text(raw):
    if isinstance(raw, dict):
        rows = raw.get('rows') or raw.get('leads') or []
        source = raw.get('source') or 'import'
        return rows, source, None
    if isinstance(raw, str):
        text = raw.lstrip('\ufeff')
        if text.lstrip().startswith('['):
            try:
                rows = json.loads(text)
            except Exception as e:
                return [], 'import', f'JSON invalide : {e}'
            return rows, 'import', None
        return _parse_csv(text)
    return [], 'import', 'Body non reconnu (attendu JSON {rows:[...]} ou texte CSV)'


def _parse_csv(text):
    rows = []
    try:
        text = text.lstrip('\ufeff')
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            return [], 'import', 'CSV sans en-tête'
        for r in reader:
            row = {k.strip().lower(): (v or '').strip() for k, v in r.items() if k}
            mapped = {}
            for src, dst in (('prenom', 'prenom'), ('email', 'email'), ('telephone', 'telephone'),
                             ('tel', 'telephone'), ('entreprise', 'entreprise'), ('societe', 'entreprise'),
                             ('site', 'site_web'), ('site_web', 'site_web'), ('adresse', 'adresse'),
                             ('ville', 'ville'), ('secteur', 'secteur'), ('rating', 'rating'),
                             ('note', 'rating'), ('nb_avis', 'nb_avis'), ('avis', 'nb_avis')):
                if src in row:
                    mapped[dst] = row[src]
            mapped['nom'] = row.get('nom') or row.get('titre') or ''
            mapped['ville'] = row.get('ville') or ''
            mapped['secteur'] = row.get('secteur') or row.get('categorie') or row.get('category') or ''
            mapped['site_web'] = mapped.get('site_web') or row.get('site') or ''
            mapped['email'] = mapped.get('email') or ''
            mapped['prenom'] = mapped.get('prenom') or ''
            if mapped['nom'] or mapped['email']:
                rows.append(mapped)
    except Exception as e:
        return [], 'import', f'Erreur parsing CSV : {e}'
    return rows, 'import', None


def _clean_lead_fields(row):
    out = {}
    for k in VALID_LEAD_FIELDS:
        if k in row and row[k] not in (None, ''):
            out[k] = row[k]
    if 'rating' in out:
        try:
            out['rating'] = float(out['rating'])
        except (TypeError, ValueError):
            out.pop('rating', None)
    if 'nb_avis' in out:
        try:
            out['nb_avis'] = int(out['nb_avis'])
        except (TypeError, ValueError):
            out.pop('nb_avis', None)
    return out


@listes_bp.route('/api/v2/listes', methods=['GET'])
def api_list_listes():
    args = request.args
    liste_id = args.get('liste_id', type=int)
    if liste_id:
        liste = listes_repo.get_liste(liste_id)
        if not liste:
            return jsonify({'success': False, 'error': 'Liste introuvable'}), 404
        return jsonify({'success': True, 'liste': liste, 'listes': [liste]})
    return jsonify({
        'success': True,
        'listes': listes_repo.list_listes(
            campagne_id=args.get('campagne_id', type=int),
            statut=args.get('statut', '') or None,
            search=args.get('search', '') or None,
        ),
    })


@listes_bp.route('/api/v2/listes', methods=['POST'])
def api_create_liste():
    data = request.get_json(silent=True) or {}
    campagne_id = data.get('campagne_id')
    if not campagne_id:
        return jsonify({'success': False, 'error': 'campagne_id requis'}), 400
    res = listes_repo.create_liste(
        campagne_id=campagne_id,
        nom=data.get('nom'),
        description=data.get('description'),
        secteur=data.get('secteur'),
        source=data.get('source') or 'manuel',
        statut=data.get('statut') or 'actif',
    )
    return jsonify(res), (201 if res['success'] else 400)


@listes_bp.route('/api/v2/listes/<int:liste_id>', methods=['PUT'])
def api_update_liste(liste_id):
    data = request.get_json(silent=True) or {}
    res = listes_repo.update_liste(liste_id, **data)
    return jsonify(res), (200 if res['success'] else 404)


@listes_bp.route('/api/v2/listes/<int:liste_id>', methods=['DELETE'])
def api_delete_liste(liste_id):
    res = listes_repo.delete_liste(liste_id)
    return jsonify(res), (200 if res['success'] else 404)


@listes_bp.route('/api/v2/listes/<int:liste_id>/archive', methods=['POST'])
def api_archive_liste(liste_id):
    data = request.get_json(silent=True) or {}
    actif = not bool(data.get('archiver', True))
    res = listes_repo.update_liste(liste_id, statut='actif' if actif else 'archive')
    return jsonify(res), (200 if res['success'] else 404)


@listes_bp.route('/api/v2/listes/<int:liste_id>/leads', methods=['GET'])
def api_list_liste_prospects(liste_id):
    liste = listes_repo.get_liste(liste_id)
    if not liste:
        return jsonify({'success': False, 'error': 'Liste introuvable'}), 404
    args = request.args
    res = prospects_repo.list_prospects(
        liste_id=liste_id,
        page=args.get('page', 1),
        limit=args.get('limit', 50),
        search=args.get('search', ''),
        statut=args.get('statut', ''),
        source=args.get('source', ''),
        secteur=args.get('secteur', ''),
        site=args.get('site', ''),
        email=args.get('email', ''),
        notes=args.get('notes', ''),
        score=args.get('score', ''),
        objectif_liste=args.get('objectif_liste', ''),
        ecarte=args.get('ecarte', ''),
        desinscrit=args.get('desinscrit', ''),
    )
    for lead in res.get('leads', []):
        lead['statut_display'] = statut_display(lead.get('statut'))
    return jsonify({'success': True, 'liste': liste, **res})


@listes_bp.route('/api/v2/listes/<int:liste_id>/leads', methods=['POST'])
def api_create_liste_prospect(liste_id):
    liste = listes_repo.get_liste(liste_id)
    if not liste:
        return jsonify({'success': False, 'error': 'Liste introuvable'}), 404
    data = request.get_json(silent=True) or {}
    res = prospects_repo.insert_prospect(
        liste_id,
        source=data.get('source') or 'manuel',
        data_extra=data.get('data_extra'),
        **_clean_lead_fields(data),
    )
    status = 201 if res['success'] else (409 if res.get('statut_dedupe') in ('doublon', 'suppression_list') else 400)
    return jsonify(res), status


@listes_bp.route('/api/v2/listes/<int:liste_id>/leads/import', methods=['POST'])
def api_import_liste_prospects(liste_id):
    liste = listes_repo.get_liste(liste_id)
    if not liste:
        return jsonify({'success': False, 'error': 'Liste introuvable'}), 404

    raw = request.get_json(silent=True)
    if raw is None:
        raw = request.get_data(as_text=True)
    rows, source, error = _json_or_text(raw)
    if error:
        return jsonify({'success': False, 'error': error}), 400

    cleaned = [_clean_lead_fields(r) for r in rows if isinstance(r, dict)]
    stats = prospects_repo.bulk_import(liste_id, cleaned, source=source)
    return jsonify({'success': True, 'liste': liste, **stats})


@listes_bp.route('/api/v2/listes/<int:liste_id>/leads', methods=['DELETE'])
def api_unlink_liste_prospects(liste_id):
    """Retire des prospects d'une liste (les déplace vers la Corbeille, non destructif)."""
    liste = listes_repo.get_liste(liste_id)
    if not liste:
        return jsonify({'success': False, 'error': 'Liste introuvable'}), 404
    data = request.get_json(silent=True) or {}
    lead_ids = data.get('lead_ids', [])
    if not lead_ids:
        return jsonify({'success': False, 'error': 'Aucun lead sélectionné'}), 400
    res = listes_repo.unlink_prospects(liste_id, lead_ids)
    return jsonify(res), (200 if res['success'] else 400)