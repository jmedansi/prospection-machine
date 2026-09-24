# -*- coding: utf-8 -*-
"""
dashboard/routes/listes.py — API v2 des listes.

Une liste est l'unité opérationnelle d'une campagne (1 scraping / 1 import / 1 secteur)
et porte directement les prospects (`prospects.liste_id`).
"""
import csv
import io
import json
import os
from datetime import datetime

from flask import Blueprint, jsonify, request

from database.connection import logger
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


# ─── Suivi temps réel des envois par liste ─────────────────────────────────
import threading
import time

_list_send_jobs: dict[int, dict] = {}


def _job_public(job):
    """Vue du job sérialisable (le champ interne `_cancel_event` n'est pas JSON)."""
    if job is None:
        return None
    return {k: v for k, v in job.items() if k != '_cancel_event'}


@listes_bp.route('/api/v2/listes/<int:liste_id>/send', methods=['POST'])
def api_send_liste_emails(liste_id):
    """Déclenche l'envoi de TOUS les emails de cette liste uniquement (sans déborder sur la campagne)."""
    liste = listes_repo.get_liste(liste_id)
    if not liste:
        return jsonify({'success': False, 'error': 'Liste introuvable'}), 404

    campagne_id = liste.get('campagne_id')
    if not campagne_id:
        return jsonify({'success': False, 'error': 'Campagne parente introuvable pour cette liste'}), 400

    from core.orchestration import candidates_for, relances_due, run_auto_send, run_relances

    data = request.get_json(silent=True) or {}
    lead_ids = [int(x) for x in (data.get('lead_ids') or []) if str(x).isdigit()] or None

    # Récupérer tous les candidats éligibles de CETTE liste uniquement
    initial_cands = candidates_for(campagne_id, limit=None, liste_id=liste_id, prospect_ids=lead_ids)
    relance_cands = relances_due(campagne_id, liste_id=liste_id, prospect_ids=lead_ids)
    total = len(initial_cands) + len(relance_cands)

    if total == 0:
        return jsonify({
            'success': True,
            'job_id': None,
            'total': 0,
            'initials': 0,
            'relances': 0,
            'message': f'Aucun email en attente d\'envoi dans la liste « {liste.get("nom", "")} » (0 prospect éligible).'
        })

    existing_job = _list_send_jobs.get(liste_id)
    if existing_job and existing_job.get('running'):
        return jsonify({
            'success': False,
            'error': f'Un envoi est déjà en cours pour la liste « {liste.get("nom", "")} »',
            'job': _job_public(existing_job)
        }), 409

    job_id = f"send_list_{liste_id}_{int(time.time() * 1000)}"
    job = {
        'job_id': job_id,
        'liste_id': liste_id,
        'liste_nom': liste.get('nom', ''),
        'campagne_id': campagne_id,
        'running': True,
        'cancelled': False,
        'current': 0,
        'total': total,
        'sent': 0,
        'failed': 0,
        'percentage': 0,
        'current_lead': None,
        'status': 'en_cours',
        'started_at': datetime.now().isoformat(),
        'finished_at': None,
        'history': []
    }
    _list_send_jobs[liste_id] = job
    _cancel_event = threading.Event()
    job['_cancel_event'] = _cancel_event  # utilisé pour couper les sleeps

    def _execute_send():
        def _prog_cb(cur, tot, cand, res):
            if job.get('cancelled'):
                raise Exception("Envoi annulé par l'utilisateur")
            job['current'] = cur
            job['percentage'] = round((cur / tot) * 100) if tot > 0 else 100
            is_ok = (res.get('statut') == 'envoye' or res.get('success') is True)
            if is_ok:
                job['sent'] += 1
            else:
                job['failed'] += 1
            lead_info = {
                'prospect_id': cand.get('id') or cand.get('prospect_id'),
                'nom': cand.get('nom') or cand.get('entreprise') or 'Prospect',
                'email': cand.get('email') or '',
                'statut': res.get('statut'),
                'success': is_ok,
                'message': res.get('message', ''),
            }
            job['current_lead'] = lead_info
            job['history'].append(lead_info)

            try:
                from dashboard.app import socketio
                if socketio:
                    socketio.emit('list_send_progress', {
                        'job_id': job['job_id'],
                        'liste_id': liste_id,
                        'liste_nom': job['liste_nom'],
                        'current': cur,
                        'total': tot,
                        'percentage': job['percentage'],
                        'sent': job['sent'],
                        'failed': job['failed'],
                        'lead': lead_info,
                    })
            except Exception:
                pass

        try:
            # 1. Envois initiaux de la liste — délai variable « comportement humain » (3 à 20s par défaut)
            lo = int(os.getenv('LIST_SEND_DELAY_MIN', '3'))
            hi = int(os.getenv('LIST_SEND_DELAY_MAX', '20'))
            list_delay = (lo, max(lo, hi))
            if initial_cands:
                run_auto_send(campagne_id, limit_per_campagne=None, manual=True,
                              liste_id=liste_id, prospect_ids=lead_ids, progress_callback=_prog_cb,
                              delay_range=list_delay, cancel_event=_cancel_event)
            # 2. Relances dues de la liste
            if relance_cands and not job.get('cancelled'):
                run_relances(campagne_id, limit_per_campagne=None, manual=True,
                             liste_id=liste_id, prospect_ids=lead_ids, progress_callback=_prog_cb,
                             delay_range=list_delay, cancel_event=_cancel_event)
            job['status'] = 'termine' if not job.get('cancelled') else 'annule'
        except Exception as e:
            logger.error("[list_send] erreur execution job %s: %s", job_id, e)
            job['status'] = 'erreur'
            job['error'] = str(e)
        finally:
            job['running'] = False
            job['finished_at'] = datetime.now().isoformat()
            try:
                from dashboard.app import socketio
                if socketio:
                    socketio.emit('list_send_done', {
                        'job_id': job['job_id'],
                        'liste_id': liste_id,
                        'liste_nom': job['liste_nom'],
                        'total': job['total'],
                        'sent': job['sent'],
                        'failed': job['failed'],
                        'status': job['status'],
                    })
            except Exception:
                pass

    threading.Thread(target=_execute_send, daemon=True).start()

    return jsonify({
        'success': True,
        'job_id': job_id,
        'total': total,
        'initials': len(initial_cands),
        'relances': len(relance_cands),
        'message': f'Envoi lancé pour {total} prospect(s) de la liste « {liste.get("nom", "")} ».'
    })


@listes_bp.route('/api/v2/listes/<int:liste_id>/send/status', methods=['GET'])
def api_send_liste_status(liste_id):
    """Retourne l'état de progression en temps réel pour l'envoi d'une liste."""
    job = _list_send_jobs.get(liste_id)
    if not job:
        return jsonify({'success': True, 'running': False, 'job': None})
    return jsonify({'success': True, 'running': job.get('running', False), 'job': _job_public(job)})


@listes_bp.route('/api/v2/listes/<int:liste_id>/send/cancel', methods=['POST'])
def api_send_liste_cancel(liste_id):
    """Annule l'envoi en cours pour cette liste."""
    job = _list_send_jobs.get(liste_id)
    if not job or not job.get('running'):
        return jsonify({'success': False, 'error': 'Aucun envoi en cours pour cette liste'}), 400
    job['cancelled'] = True
    job['status'] = 'annule'
    # Réveil immédiat du sleep inter-envois
    ev = job.get('_cancel_event')
    if ev:
        ev.set()
    return jsonify({'success': True, 'message': 'Envoi de la liste en cours d\'annulation'})