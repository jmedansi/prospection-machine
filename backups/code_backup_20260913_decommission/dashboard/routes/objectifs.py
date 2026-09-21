# -*- coding: utf-8 -*-
"""
dashboard/routes/objectifs.py — API v2 pilotée par objectif.

Flux demandé par l'utilisateur :
  1. l'utilisateur crée un objectif (nom libre, ex. « Refonte site web ») ;
  2. il importe des leads (CSV / JSON / saisie) DANS cet objectif ;
  3. la page Leads ne montre que les leads de l'objectif sélectionné.

Tout est sous /api/v2 pour ne pas casser l'API legacy /api/leads.
"""
import csv
import io
import json

from flask import Blueprint, jsonify, request

from core.state_machine import transition_prospect, statut_display, VALID_TRANSITIONS, STATUT_LABELS
from database import objectifs as objectifs_repo
from database import prospects as prospects_repo

objectifs_bp = Blueprint('objectifs_bp', __name__)

VALID_LEAD_FIELDS = {
    'nom', 'prenom', 'email', 'telephone', 'entreprise', 'site_web', 'adresse',
    'ville', 'secteur', 'rating', 'nb_avis', 'source', 'score',
}


def _json_or_text(raw):
    """Retourne (rows, error). Accepte un body JSON {rows:[...], leads:[...]} ou un texte CSV."""
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
        hinted = False
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
                    hinted = True
            mapped['nom'] = row.get('nom') or row.get('titre') or ''
            mapped['ville'] = row.get('ville') or ''
            mapped['secteur'] = row.get('secteur') or row.get('categorie') or row.get('category') or ''
            mapped['site_web'] = mapped.get('site_web') or row.get('site') or ''
            mapped['email'] = mapped.get('email') or ''
            mapped['prenom'] = mapped.get('prenom') or ''
            if mapped['nom'] or mapped['email']:
                rows.append(mapped)
        if not hinted and any(r for r in rows if r.get('nom') or r.get('email')):
            pass  # déjà mappé via nom/ville
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


@objectifs_bp.route('/api/v2/auto-send', methods=['GET'])
def api_auto_send_status():
    return jsonify({'success': True, 'enabled': objectifs_repo.get_auto_send_enabled()})


@objectifs_bp.route('/api/v2/auto-send', methods=['PUT'])
def api_auto_send_set():
    data = request.get_json(silent=True) or {}
    enabled = bool(data.get('enabled', True))
    objectifs_repo.set_auto_send_enabled(enabled)
    return jsonify({'success': True, 'enabled': enabled})


@objectifs_bp.route('/api/v2/objectifs/<int:objectif_id>/send', methods=['POST'])
def api_send_objectif_now(objectif_id):
    """Déclenchement manuel (ignore envoi_auto + kill-switch) : initial + relances dues."""
    from core.orchestration import run_auto_send, run_relances
    data = request.get_json(silent=True) or {}
    limit = int(data.get('limit', 0) or 10)
    init_res = run_auto_send(objectif_id, limit_per_objectif=limit, manual=True)
    rel_res = run_relances(objectif_id, limit_per_objectif=limit, manual=True)
    if not init_res['success'] or not rel_res['success']:
        return jsonify({'success': False, 'error': init_res.get('error') or rel_res.get('error')}), 400
    return jsonify({
        'success': True,
        'initials': init_res.get('total', 0),
        'relances': rel_res.get('total', 0),
        'runs': init_res.get('runs', []),
        'relance_runs': rel_res.get('runs', []),
    })


@objectifs_bp.route('/api/v2/objectifs/<int:objectif_id>/sequence', methods=['GET'])
def api_objectif_sequence(objectif_id):
    """Templates applicables à un objectif (dédiés + génériques), par position."""
    from envoi import template_registry
    obj = objectifs_repo.get_objectif(objectif_id)
    if not obj:
        return jsonify({'success': False, 'error': 'Objectif introuvable'}), 404
    templates = template_registry.get_templates(objectif_id, include_inactifs=True)
    return jsonify({'success': True, 'templates': templates})


@objectifs_bp.route('/api/v2/objectifs/<int:objectif_id>/sequence', methods=['POST'])
def api_objectif_sequence_add(objectif_id):
    """Ajoute une étape (position + delai_jours) dédiée à l'objectif."""
    from envoi import template_registry
    data = request.get_json(silent=True) or {}
    if not objectifs_repo.get_objectif(objectif_id):
        return jsonify({'success': False, 'error': 'Objectif introuvable'}), 404
    res = template_registry.add_or_update(
        objectif_id=objectif_id,
        nom=data.get('nom', ''),
        objet=data.get('objet', ''),
        corps=data.get('corps', ''),
        position=data.get('position', 0),
        delai_jours=data.get('delai_jours', 0),
        canal=data.get('canal', 'email'),
    )
    return jsonify(res), (201 if res['success'] else 400)


@objectifs_bp.route('/api/v2/sequence-templates/<int:template_id>', methods=['PUT'])
def api_template_update(template_id):
    from envoi import template_registry
    data = request.get_json(silent=True) or {}
    res = template_registry.update(
        template_id,
        objet=data.get('objet'),
        corps=data.get('corps'),
        delai_jours=data.get('delai_jours'),
        actif=data.get('actif'),
    )
    return jsonify(res), (200 if res['success'] else 404)


@objectifs_bp.route('/api/v2/sequence-templates/<int:template_id>', methods=['DELETE'])
def api_template_delete(template_id):
    from envoi import template_registry
    template_registry.delete(template_id)
    return jsonify({'success': True})


@objectifs_bp.route('/api/v2/statuts/transitions', methods=['GET'])
def api_statuts_transitions():
    """Transitions autorisées (machine à états) + libellés, pour l'UI (file humaine)."""
    transitions = {s: sorted(set(STATUT_LABELS) & t)
                   for s, t in VALID_TRANSITIONS.items()}
    return jsonify({'success': True,
                    'transitions': transitions,
                    'labels': STATUT_LABELS,
                    'statut_display': {s: statut_display(s) for s in STATUT_LABELS}})


@objectifs_bp.route('/api/v2/objectifs', methods=['GET'])
def api_list_objectifs():
    return jsonify({'success': True, 'objectifs': objectifs_repo.list_objectifs()})


@objectifs_bp.route('/api/v2/objectifs', methods=['POST'])
def api_create_objectif():
    data = request.get_json(silent=True) or {}
    nom = data.get('nom')
    res = objectifs_repo.create_objectif(
        nom,
        description=data.get('description'),
        segment=data.get('segment'),
        validation_telegram=data.get('validation_telegram'),
        backend_pref=data.get('backend_pref'),
        max_touches=data.get('max_touches'),
    )
    status = 201 if res['success'] else 400
    return jsonify(res), status


@objectifs_bp.route('/api/v2/objectifs/<int:objectif_id>', methods=['PUT'])
def api_update_objectif(objectif_id):
    data = request.get_json(silent=True) or {}
    res = objectifs_repo.update_objectif(objectif_id, **data)
    status = 200 if res['success'] else 404
    return jsonify(res), status


@objectifs_bp.route('/api/v2/objectifs/<int:objectif_id>', methods=['DELETE'])
def api_delete_objectif(objectif_id):
    res = objectifs_repo.delete_objectif(objectif_id)
    return jsonify(res), (200 if res['success'] else 404)


@objectifs_bp.route('/api/v2/objectifs/<int:objectif_id>/stats', methods=['GET'])
def api_objectif_stats(objectif_id):
    obj = objectifs_repo.get_objectif(objectif_id)
    if not obj:
        return jsonify({'success': False, 'error': 'Objectif introuvable'}), 404
    from database.connection import get_conn
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM prospects WHERE objectif_id = ?", (objectif_id,)).fetchone()['n']
        breakdown_rows = conn.execute(
            "SELECT statut, COUNT(*) AS n FROM prospects WHERE objectif_id = ? GROUP BY statut",
            (objectif_id,),
        ).fetchall()
    breakdown = {}
    for r in breakdown_rows:
        breakdown[r['statut']] = {
            'count': r['n'],
            **statut_display(r['statut']),
        }
    repondu = sum(v['count'] for k, v in breakdown.items()
                  if k in {'a_traiter_humain', 'rdv_obtenu', 'pas_interesse', 'a_relancer_plus_tard'})
    return jsonify({
        'success': True,
        'objectif': obj,
        'stats': {'total': total, 'repondu': repondu, 'breakdown': breakdown},
    })


@objectifs_bp.route('/api/v2/objectifs/<int:objectif_id>/leads', methods=['GET'])
def api_list_prospects(objectif_id):
    args = request.args
    res = prospects_repo.list_prospects(
        objectif_id,
        page=args.get('page', 1),
        limit=args.get('limit', 50),
        search=args.get('search', ''),
        statut=args.get('statut', ''),
    )
    for lead in res.get('leads', []):
        lead['statut_display'] = statut_display(lead.get('statut'))
    return jsonify({'success': True, **res})


@objectifs_bp.route('/api/v2/objectifs/<int:objectif_id>/leads', methods=['POST'])
def api_create_prospect(objectif_id):
    data = request.get_json(silent=True) or {}
    res = prospects_repo.insert_prospect(
        objectif_id,
        source=data.get('source') or 'manuel',
        data_extra=data.get('data_extra'),
        **_clean_lead_fields(data),
    )
    status = 201 if res['success'] else (409 if res.get('statut_dedupe') in ('doublon', 'suppression_list') else 400)
    return jsonify(res), status


@objectifs_bp.route('/api/v2/objectifs/<int:objectif_id>/leads/import', methods=['POST'])
def api_import_prospects(objectif_id):
    obj = objectifs_repo.get_objectif(objectif_id)
    if not obj:
        return jsonify({'success': False, 'error': 'Objectif introuvable'}), 404

    raw = request.get_json(silent=True)
    if raw is None:
        raw = request.get_data(as_text=True)
    rows, source, error = _json_or_text(raw)
    if error:
        return jsonify({'success': False, 'error': error}), 400

    cleaned = [_clean_lead_fields(r) for r in rows if isinstance(r, dict)]
    stats = prospects_repo.bulk_import(objectif_id, cleaned, source=source)
    return jsonify({'success': True, **stats})


@objectifs_bp.route('/api/v2/leads/<int:prospect_id>', methods=['PUT'])
def api_update_prospect(prospect_id):
    data = request.get_json(silent=True) or {}
    res = prospects_repo.update_prospect(prospect_id, **_clean_lead_fields(data))
    return jsonify(res), (200 if res['success'] else 404)


@objectifs_bp.route('/api/v2/leads/<int:prospect_id>', methods=['DELETE'])
def api_delete_prospect(prospect_id):
    res = prospects_repo.delete_prospect(prospect_id)
    return jsonify(res), (200 if res['success'] else 404)


@objectifs_bp.route('/api/v2/leads/<int:prospect_id>/ecarter', methods=['POST'])
def api_ecarter_prospect(prospect_id):
    data = request.get_json(silent=True) or {}
    res = prospects_repo.set_ecarte(prospect_id, bool(data.get('ecarte', True)))
    return jsonify(res), (200 if res['success'] else 404)


@objectifs_bp.route('/api/v2/leads/<int:prospect_id>/desinscrire', methods=['POST'])
def api_desinscrire_prospect(prospect_id):
    data = request.get_json(silent=True) or {}
    en = bool(data.get('ne_plus_contacter', True))
    res = prospects_repo.set_ne_plus_contacter(prospect_id, en, raison=data.get('raison') or 'desinscription')
    return jsonify(res), (200 if res['success'] else 404)


@objectifs_bp.route('/api/v2/leads/<int:prospect_id>', methods=['GET'])
def api_get_prospect(prospect_id):
    """Détail d'un prospect (file humaine) : infos + events (payload JSON parsé)."""
    p = prospects_repo.get_prospect(prospect_id)
    if not p:
        return jsonify({'success': False, 'error': 'Prospect introuvable'}), 404
    return jsonify({'success': True, 'lead': p})


@objectifs_bp.route('/api/v2/leads/<int:prospect_id>/statut', methods=['PUT'])
def api_transition_prospect(prospect_id):
    data = request.get_json(silent=True) or {}
    nouveau = data.get('statut')
    if not nouveau:
        return jsonify({'success': False, 'error': 'Le champ statut est requis'}), 400
    res = transition_prospect(prospect_id, nouveau, reason=data.get('reason') or 'manuelle', payload=data.get('payload'))
    status = 200 if res['success'] else 400
    return jsonify(res), status