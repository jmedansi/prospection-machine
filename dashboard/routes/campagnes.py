# -*- coding: utf-8 -*-
"""
dashboard/routes/campagnes.py — API v2 pilotée par campagne (remplace « objectif »).

Une campagne porte la configuration (max_touches, validation_telegram, envoi_auto,
backend_pref) partagée par ses listes. Les prospects sont insérés dans une LISTE
de la campagne (liste par défaut auto-créée si aucune liste cible n'est précisée).

Tout est sous /api/v2 pour ne pas casser l'API legacy /api/leads.
"""
import csv
import io
import json

from flask import Blueprint, jsonify, request

from core.objectif_registry import get_or_create_liste
from core.state_machine import transition_prospect, statut_display, VALID_TRANSITIONS, STATUT_LABELS
from database import campagnes as campagnes_repo
from database import prospects as prospects_repo
from database.connection import get_conn

campagnes_bp = Blueprint('campagnes_bp', __name__)

VALID_LEAD_FIELDS = {
    'nom', 'prenom', 'email', 'telephone', 'entreprise', 'site_web', 'adresse',
    'ville', 'secteur', 'rating', 'nb_avis', 'source', 'score', 'note',
}


def _json_or_text(raw):
    """Retourne (rows, source, error). Accepte un body JSON {rows:[...]} ou un texte CSV."""
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


@campagnes_bp.route('/api/v2/auto-send', methods=['GET'])
def api_auto_send_status():
    return jsonify({'success': True, 'enabled': campagnes_repo.get_auto_send_enabled()})


@campagnes_bp.route('/api/v2/auto-send', methods=['PUT'])
def api_auto_send_set():
    data = request.get_json(silent=True) or {}
    enabled = bool(data.get('enabled', True))
    campagnes_repo.set_auto_send_enabled(enabled)
    return jsonify({'success': True, 'enabled': enabled})


@campagnes_bp.route('/api/v2/campagnes/<int:campagne_id>/send', methods=['POST'])
def api_send_campagne_now(campagne_id):
    """Déclenchement manuel (ignore envoi_auto + kill-switch) : initial + relances dues.

    `liste_id` optionnel : bouton « Envoyer » d'une liste précise → restreint
    l'initial ET les relances aux prospects de cette liste uniquement (sinon
    toute la campagne).
    """
    from core.orchestration import run_auto_send, run_relances
    data = request.get_json(silent=True) or {}
    raw_limit = data.get('limit', 0)
    limit = None
    try:
        if raw_limit is not None and int(raw_limit) > 0:
            limit = int(raw_limit)
    except (TypeError, ValueError):
        limit = None
    liste_id = data.get('liste_id')
    lead_ids = data.get('lead_ids') or None
    init_res = run_auto_send(campagne_id, limit_per_campagne=limit, manual=True,
                             liste_id=liste_id, prospect_ids=lead_ids)
    rel_res = run_relances(campagne_id, limit_per_campagne=limit, manual=True,
                           liste_id=liste_id, prospect_ids=lead_ids)
    if not init_res['success'] or not rel_res['success']:
        return jsonify({'success': False, 'error': init_res.get('error') or rel_res.get('error')}), 400
    return jsonify({
        'success': True,
        'initials': init_res.get('total', 0),
        'relances': rel_res.get('total', 0),
        'runs': init_res.get('runs', []),
        'relance_runs': rel_res.get('runs', []),
    })


@campagnes_bp.route('/api/v2/campagnes/<int:campagne_id>/sequence', methods=['GET'])
def api_campagne_sequence(campagne_id):
    """Templates applicables à une campagne (dédiés + génériques), par position."""
    from envoi import template_registry
    if not campagnes_repo.get_campagne(campagne_id):
        return jsonify({'success': False, 'error': 'Campagne introuvable'}), 404
    templates = template_registry.get_templates(campagne_id, include_inactifs=True)
    return jsonify({'success': True, 'templates': templates})


@campagnes_bp.route('/api/v2/campagnes/<int:campagne_id>/sequence', methods=['POST'])
def api_campagne_sequence_add(campagne_id):
    """Ajoute une étape (position + delai_jours) dédiée à la campagne."""
    from envoi import template_registry
    data = request.get_json(silent=True) or {}
    if not campagnes_repo.get_campagne(campagne_id):
        return jsonify({'success': False, 'error': 'Campagne introuvable'}), 404
    res = template_registry.add_or_update(
        campagne_id=campagne_id,
        nom=data.get('nom', ''),
        objet=data.get('objet', ''),
        corps=data.get('corps', ''),
        position=data.get('position', 0),
        delai_jours=data.get('delai_jours', 0),
        canal=data.get('canal', 'email'),
    )
    return jsonify(res), (201 if res['success'] else 400)


@campagnes_bp.route('/api/v2/sequence-templates/<int:template_id>', methods=['PUT'])
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


@campagnes_bp.route('/api/v2/sequence-templates/<int:template_id>', methods=['DELETE'])
def api_template_delete(template_id):
    from envoi import template_registry
    template_registry.delete(template_id)
    return jsonify({'success': True})


@campagnes_bp.route('/api/v2/statuts/transitions', methods=['GET'])
def api_statuts_transitions():
    """Transitions autorisées (machine à états) + libellés, pour l'UI (file humaine)."""
    transitions = {s: sorted(set(STATUT_LABELS) & t)
                   for s, t in VALID_TRANSITIONS.items()}
    return jsonify({'success': True,
                    'transitions': transitions,
                    'labels': STATUT_LABELS,
                    'statut_display': {s: statut_display(s) for s in STATUT_LABELS}})


@campagnes_bp.route('/api/v2/campagnes', methods=['GET'])
def api_list_campagnes():
    return jsonify({'success': True, 'campagnes': campagnes_repo.list_campagnes()})


@campagnes_bp.route('/api/v2/campagnes', methods=['POST'])
def api_create_campagne():
    data = request.get_json(silent=True) or {}
    nom = data.get('nom')
    res = campagnes_repo.create_campagne(
        nom,
        description=data.get('description'),
        segment=data.get('segment'),
        validation_telegram=data.get('validation_telegram'),
        backend_pref=data.get('backend_pref'),
        max_touches=data.get('max_touches'),
    )
    status = 201 if res['success'] else 400
    return jsonify(res), status


@campagnes_bp.route('/api/v2/campagnes/<int:campagne_id>', methods=['PUT'])
def api_update_campagne(campagne_id):
    data = request.get_json(silent=True) or {}
    res = campagnes_repo.update_campagne(campagne_id, **data)
    status = 200 if res['success'] else 404
    return jsonify(res), status


@campagnes_bp.route('/api/v2/campagnes/<int:campagne_id>', methods=['DELETE'])
def api_delete_campagne(campagne_id):
    res = campagnes_repo.delete_campagne(campagne_id)
    return jsonify(res), (200 if res['success'] else 404)


@campagnes_bp.route('/api/v2/campagnes/<int:campagne_id>/stats', methods=['GET'])
def api_campagne_stats(campagne_id):
    obj = campagnes_repo.get_campagne(campagne_id)
    if not obj:
        return jsonify({'success': False, 'error': 'Campagne introuvable'}), 404
    from database.connection import get_conn
    with get_conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM prospects p JOIN listes l ON p.liste_id = l.id WHERE l.campagne_id = ?",
            (campagne_id,),
        ).fetchone()['n']
        breakdown_rows = conn.execute(
            """SELECT p.statut, COUNT(*) AS n FROM prospects p
               JOIN listes l ON p.liste_id = l.id
               WHERE l.campagne_id = ? GROUP BY p.statut""",
            (campagne_id,),
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
        'campagne': obj,
        'stats': {'total': total, 'repondu': repondu, 'breakdown': breakdown},
    })


@campagnes_bp.route('/api/v2/leads', methods=['GET'])
def api_list_all_prospects():
    """Tous les prospects (toutes campagnes) pour la vue « toutes campagnes » v2,
    chacun portant campagne_id / campagne_nom / liste_id / liste_nom."""
    args = request.args
    res = prospects_repo.list_prospects(
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
        liste_id=args.get('liste_id', type=int),
        ecarte=args.get('ecarte', ''),
        desinscrit=args.get('desinscrit', ''),
    )
    for lead in res.get('leads', []):
        lead['statut_display'] = statut_display(lead.get('statut'))
    return jsonify({'success': True, **res})


@campagnes_bp.route('/api/v2/campagnes/<int:campagne_id>/leads', methods=['GET'])
def api_list_prospects(campagne_id):
    args = request.args
    res = prospects_repo.list_prospects(
        campagne_id=campagne_id,
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
        liste_id=args.get('liste_id', type=int),
        ecarte=args.get('ecarte', ''),
        desinscrit=args.get('desinscrit', ''),
    )
    for lead in res.get('leads', []):
        lead['statut_display'] = statut_display(lead.get('statut'))
    return jsonify({'success': True, **res})


@campagnes_bp.route('/api/v2/campagnes/<int:campagne_id>/leads', methods=['POST'])
def api_create_prospect(campagne_id):
    """Insertion dans la liste par défaut de la campagne (auto-créée au besoin)."""
    data = request.get_json(silent=True) or {}
    liste_id = get_or_create_liste(campagne_id)
    if not liste_id:
        return jsonify({'success': False, 'error': 'Campagne introuvable'}), 404
    res = prospects_repo.insert_prospect(
        liste_id,
        source=data.get('source') or 'manuel',
        data_extra=data.get('data_extra'),
        **_clean_lead_fields(data),
    )
    status = 201 if res['success'] else (409 if res.get('statut_dedupe') in ('doublon', 'suppression_list') else 400)
    return jsonify(res), status


@campagnes_bp.route('/api/v2/campagnes/<int:campagne_id>/leads/import', methods=['POST'])
def api_import_prospects(campagne_id):
    """Import CSV/JSON dans la liste par défaut de la campagne."""
    if not campagnes_repo.get_campagne(campagne_id):
        return jsonify({'success': False, 'error': 'Campagne introuvable'}), 404
    liste_id = get_or_create_liste(campagne_id)

    raw = request.get_json(silent=True)
    if raw is None:
        raw = request.get_data(as_text=True)
    rows, source, error = _json_or_text(raw)
    if error:
        return jsonify({'success': False, 'error': error}), 400

    cleaned = [_clean_lead_fields(r) for r in rows if isinstance(r, dict)]
    stats = prospects_repo.bulk_import(liste_id, cleaned, source=source)
    return jsonify({'success': True, **stats})


@campagnes_bp.route('/api/v2/leads/<int:prospect_id>', methods=['PUT'])
def api_update_prospect(prospect_id):
    data = request.get_json(silent=True) or {}
    cleaned = _clean_lead_fields(data)
    if 'data_extra' in data and isinstance(data['data_extra'], dict):
        cleaned['data_extra'] = data['data_extra']
    res = prospects_repo.update_prospect(prospect_id, **cleaned)
    return jsonify(res), (200 if res['success'] else 404)


@campagnes_bp.route('/api/v2/leads/<int:prospect_id>', methods=['DELETE'])
def api_delete_prospect(prospect_id):
    res = prospects_repo.delete_prospect(prospect_id)
    return jsonify(res), (200 if res['success'] else 404)


@campagnes_bp.route('/api/v2/leads/<int:prospect_id>/ecarter', methods=['POST'])
def api_ecarter_prospect(prospect_id):
    data = request.get_json(silent=True) or {}
    res = prospects_repo.set_ecarte(prospect_id, bool(data.get('ecarte', True)))
    return jsonify(res), (200 if res['success'] else 404)


@campagnes_bp.route('/api/v2/leads/<int:prospect_id>/desinscrire', methods=['POST'])
def api_desinscrire_prospect(prospect_id):
    data = request.get_json(silent=True) or {}
    en = bool(data.get('ne_plus_contacter', True))
    res = prospects_repo.set_ne_plus_contacter(prospect_id, en, raison=data.get('raison') or 'desinscription')
    return jsonify(res), (200 if res['success'] else 404)


def _coerce_ids(raw) -> list[int]:
    if not raw:
        return []
    if isinstance(raw, (int, str)):
        raw = [raw]
    out = []
    for x in raw:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            continue
    return out


@campagnes_bp.route('/api/v2/leads/bulk/ecarter', methods=['POST'])
def api_bulk_ecarter():
    """Écarter / réintégrer une sélection de prospects en une seule requête."""
    data = request.get_json(silent=True) or {}
    ids = _coerce_ids(data.get('lead_ids'))
    if not ids:
        return jsonify({'success': False, 'error': 'Aucun lead_id fourni'}), 400
    ecarte = bool(data.get('ecarte', True))
    ok, errors = 0, []
    for pid in ids:
        res = prospects_repo.set_ecarte(pid, ecarte)
        if res['success']:
            ok += 1
        else:
            errors.append({'prospect_id': pid, 'error': res.get('error') or 'introuvable'})
    return jsonify({'success': True, 'updated': ok, 'errors': errors, 'ecarte': ecarte})


@campagnes_bp.route('/api/v2/leads/bulk/desinscrire', methods=['POST'])
def api_bulk_desinscrire():
    """Désinscrire / réactiver une sélection de prospects (opposition globale)."""
    data = request.get_json(silent=True) or {}
    ids = _coerce_ids(data.get('lead_ids'))
    if not ids:
        return jsonify({'success': False, 'error': 'Aucun lead_id fourni'}), 400
    en = bool(data.get('ne_plus_contacter', True))
    ok, errors = 0, []
    for pid in ids:
        res = prospects_repo.set_ne_plus_contacter(pid, en, raison=data.get('raison') or 'desinscription')
        if res['success']:
            ok += 1
        else:
            errors.append({'prospect_id': pid, 'error': res.get('error') or 'introuvable'})
    return jsonify({'success': True, 'updated': ok, 'errors': errors, 'ne_plus_contacter': en})


@campagnes_bp.route('/api/v2/leads/bulk', methods=['DELETE'])
def api_bulk_delete():
    """Suppression définitive d'une sélection de prospects."""
    data = request.get_json(silent=True) or {}
    ids = _coerce_ids(data.get('lead_ids'))
    if not ids:
        return jsonify({'success': False, 'error': 'Aucun lead_id fourni'}), 400
    ok, errors = 0, []
    for pid in ids:
        res = prospects_repo.delete_prospect(pid)
        if res['success']:
            ok += 1
        else:
            errors.append({'prospect_id': pid, 'error': res.get('error') or 'introuvable'})
    return jsonify({'success': True, 'deleted': ok, 'errors': errors})


@campagnes_bp.route('/api/v2/leads/<int:prospect_id>', methods=['GET'])
def api_get_prospect(prospect_id):
    """Détail d'un prospect (file humaine) : infos + events (payload JSON parsé)."""
    p = prospects_repo.get_prospect(prospect_id)
    if not p:
        return jsonify({'success': False, 'error': 'Prospect introuvable'}), 404
    return jsonify({'success': True, 'lead': p})


@campagnes_bp.route('/api/v2/leads/<int:prospect_id>/statut', methods=['PUT'])
def api_transition_prospect(prospect_id):
    data = request.get_json(silent=True) or {}
    nouveau = data.get('statut')
    if not nouveau:
        return jsonify({'success': False, 'error': 'Le champ statut est requis'}), 400
    res = transition_prospect(prospect_id, nouveau, reason=data.get('reason') or 'manuelle', payload=data.get('payload'))
    status = 200 if res['success'] else 400
    return jsonify(res), status


def _render_v2_email(prospect):
    """Rendu de l'email correspondant a la PROCHAINE touche d'un prospect v2,
    tel qu'il sera envoye (HTML final).

    La position affichee depend du statut du prospect :
      - 'qualifie'    -> position 0 (Envoi initial)
      - 'en_sequence' -> position 1 (Relance 1)
      - 'relance_1'   -> position 2 (Relance 2)
      - 'relance_2'   -> position 3 (Relance 3)

    REGLE D'AFFICHAGE : onglet Email = prochain mail a envoyer.
    REGLE D'ENVOI (inchangee) : initial=manuel, relances=Telegram.
    Source de verite : email redige pour le prospect (IA/manuel).
    Repli : template de campagne si aucun email redige.
    """

    from envoi.sequence_engine import get_custom_step_email, STATUT_NEXT_POSITION
    from envoi import email_shell, template_registry

    cid = prospect.get('campagne_id')
    obj = campagnes_repo.get_campagne(cid) if cid else None
    profil = (obj or {}).get('objectif_principale') or ''

    # Determiner la prochaine position selon le statut du prospect
    statut = prospect.get('statut') or 'qualifie'
    position = STATUT_NEXT_POSITION.get(statut, 0)  # 0 si qualifie ou etat final
    STEP_LABELS = {0: 'Envoi initial', 1: 'Relance 1', 2: 'Relance 2', 3: 'Relance 3'}
    step_label = STEP_LABELS.get(position, f'Etape {position}')

    # 1. Priorité 1 : Email rédigé pour le prospect (agent IA ou manuel)
    custom = get_custom_step_email(prospect, position)
    if custom:
        objet, corps = custom
        return {
            'objet': objet, 'corps': email_shell.build_html_email(objet, corps),
            'corps_texte': corps, 'profil': profil, 'step': position,
            'step_label': step_label, 'source': 'ia_redaction',
            'template_id': None,
        }

    # 2. Repli : Template de la campagne
    if cid:
        template = template_registry.get_step(cid, position=position)
        if template:
            rendered = template_registry.render_template(template, prospect)
            objet = rendered['objet']
            corps = rendered['corps']
            return {
                'objet': objet, 'corps': email_shell.build_html_email(objet, corps),
                'corps_texte': corps, 'profil': profil, 'step': position,
                'step_label': step_label, 'source': 'template',
                'template_id': template.get('id'),
            }

    return {
        'objet': '', 'corps': '', 'corps_texte': '', 'profil': profil,
        'step': position, 'step_label': step_label, 'source': 'none', 'template_id': None,
    }


@campagnes_bp.route('/api/v2/leads/<int:prospect_id>/email', methods=['GET'])
def api_v2_lead_email(prospect_id):
    """Aperçu de l'email v2 d'un prospect tel qu'il sera envoyé (HTML final)."""
    p = prospects_repo.get_prospect(prospect_id)
    if not p:
        return jsonify({'success': False, 'error': 'Prospect introuvable'}), 404
    return jsonify({'success': True, 'email': _render_v2_email(p)})


@campagnes_bp.route('/api/v2/leads/<int:prospect_id>/email-preview', methods=['GET'])
def api_v2_lead_email_preview(prospect_id):
    """Prévisualisation du contenu EXACT qui SERA envoyé pour la touche demandée.

    Partage le même code que l'envoi (`sequence_engine.prepare_initial` /
    `prepare_step` en dry_run) → la prévisualisation reflète la source de
    vérité (`data_extra.email_*` / colonnes email_* du prospect), jamais un
    template de séquence.

    Query : `?position=0|1|2|3` (0 = initial par défaut).
    Retour : objet + corps (texte déjà rendu, prêt pour l'envoi), `source` :
    - 'ia'               → contenu rédigé (source de vérité) ;
    - 'template_fallback'→ code mort côté Option A (toujours 'ia' ici), réservé.
    400 `raison='pas_email_ia'` si aucune étape de la séquence n'a de contenu
    rédigé → l'UI affiche un message « email non rédigé ».
    """
    from envoi import sequence_engine

    p = prospects_repo.get_prospect(prospect_id)
    if not p:
        return jsonify({'success': False, 'error': 'Prospect introuvable'}), 404
    cid = p.get('campagne_id')
    position = request.args.get('position', default=0, type=int)
    if position == 0:
        prep = sequence_engine.prepare_initial(cid, prospect_id, dry_run=True)
    else:
        prep = sequence_engine.prepare_step(cid, prospect_id, position,
                                            'Relance %d' % position, dry_run=True)
    if not prep.get('ok'):
        return jsonify({'success': False,
                        'raison': prep.get('raison'),
                        'message': prep.get('message') or prep.get('raison')}), 400
    return jsonify({
        'success': True,
        'objet': prep['objet'],
        'corps': prep['corps'],
        'source': 'ia' if prep.get('template') is None else 'template_fallback',
    })


@campagnes_bp.route('/api/v2/leads/<int:prospect_id>/email/test', methods=['POST'])
def api_v2_lead_email_test(prospect_id):
    """Envoie un email de test (rendu v2) à une adresse (défaut: RESEND_SENDER_EMAIL)."""
    import os

    from envoi import gateway

    p = prospects_repo.get_prospect(prospect_id)
    if not p:
        return jsonify({'success': False, 'error': 'Prospect introuvable'}), 404
    rendered = _render_v2_email(p)
    if rendered['source'] == 'none' or not rendered['corps']:
        return jsonify({'success': False, 'error': 'Aucun email à tester (ni template, ni contenu enregistré)'}), 400
    data = request.get_json(silent=True) or {}
    to = (data.get('to') or '').strip() or os.getenv('EMAIL_TEST_TO') or os.getenv('RESEND_SENDER_EMAIL') or os.getenv('BREVO_SENDER_EMAIL')
    if not to:
        return jsonify({'success': False, 'error': "Adresse de test introuvable : fournir 'to' ou configurer EMAIL_TEST_TO"}), 400
    resp = gateway.envoyer({
        'to': to,
        'nom': p.get('entreprise') or p.get('nom') or p.get('prenom') or 'Test',
        'subject': '[TEST] %s' % rendered['objet'],
        'corps': rendered['corps'],
        'campagne_id': p.get('campagne_id'),
        'dry_run': False,
        'no_quota': True,
        'ignore_quota': True,
    })
    if not resp.get('success'):
        return jsonify({'success': False, 'error': resp.get('erreur') or resp.get('statut') or 'Envoi test échoué'}), 400
    return jsonify({'success': True, 'message_id': resp.get('message_id'), 'to': to})


@campagnes_bp.route('/api/v2/leads/<int:prospect_id>/email/send', methods=['POST'])
def api_v2_lead_email_send(prospect_id):
    """Envoie la prochaine touche du prospect.

    - `qualifie`   → initial : envoi MANUEL direct (règle : 1er mail manuel, sans exception).
    - sinon        → relance : TOUJOURS via validation Telegram (approval='telegram'),
      aucune relance ne part sans ✅.
    """
    from envoi import sequence_engine

    p = prospects_repo.get_prospect(prospect_id)
    if not p:
        return jsonify({'success': False, 'error': 'Prospect introuvable'}), 404
    cid = p.get('campagne_id')
    if p.get('statut') == 'qualifie':
        res = sequence_engine.send_initial(cid, prospect_id, humanize_on=False)
    else:
        res = sequence_engine.send_relance(cid, prospect_id, humanize_on=False, approval='telegram')
    if not isinstance(res, dict):
        res = {'message': str(res)}
    hard_fail = res.get('success') is False and not res.get('statut')
    return jsonify({'success': res.get('success', True), 'statut': res.get('statut'), 'message': res.get('message'),
                    **({'callback_id': res['callback_id']} if res.get('callback_id') else {}),
                    **({'id': res['id']} if res.get('id') else {})}), (400 if hard_fail else 200)


@campagnes_bp.route('/api/v2/leads/<int:prospect_id>/reply', methods=['POST'])
def api_v2_lead_custom_reply(prospect_id):
    """Envoie un email de réponse ou relance personnalisée pour ce prospect."""
    import json
    from envoi import gateway, threading, email_shell

    p = prospects_repo.get_prospect(prospect_id)
    if not p:
        return jsonify({'success': False, 'error': 'Prospect introuvable'}), 404
    if not p.get('email'):
        return jsonify({'success': False, 'error': 'Ce prospect n\'a pas d\'adresse email'}), 400

    data = request.get_json(silent=True) or {}
    subject = (data.get('subject') or data.get('objet') or '').strip()
    body = (data.get('body') or data.get('corps') or '').strip()

    if not body:
        return jsonify({'success': False, 'error': 'Le corps de l\'email ne peut pas être vide'}), 400

    # Chaîner les headers RFC 2822
    prior = threading.last_touch_event(p.get('events'))
    if prior and prior.get('message_id'):
        in_reply_to = prior.get('message_id')
        references = threading.extend_references(prior.get('references_header'), prior.get('message_id'))
        parent_event_id = prior.get('id')
        thread_id = prior.get('thread_id') or prior.get('id')
    else:
        in_reply_to = references = parent_event_id = thread_id = None

    if not subject:
        init_obj = p.get('email_objet') or 'Votre activité'
        subject = threading.ensure_re(init_obj)

    cid = p.get('campagne_id')
    resp = gateway.envoyer({
        'to': p['email'],
        'nom': p.get('entreprise') or p.get('nom') or '',
        'subject': subject,
        'corps': body,
        'campagne_id': cid,
        'dry_run': False,
        'in_reply_to': in_reply_to,
        'references': references,
    })

    if not resp.get('success'):
        return jsonify({'success': False, 'error': resp.get('erreur') or resp.get('statut') or 'Échec envoi'}), 400

    mailbox = resp.get('boite') or {}
    payload = {
        'step': 'reponse_manuelle',
        'objet': subject,
        'corps': body,
        'snippet': body[:250],
        'backend': mailbox.get('backend'),
        'mailbox_email': mailbox.get('email'),
        'rfc_message_id': resp.get('message_id'),
        'in_reply_to': in_reply_to,
        'references': references,
    }
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO prospect_events
               (prospect_id, campagne_id, event_type, payload, mailbox_id, message_id,
                in_reply_to, references_header, direction, parent_event_id, thread_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (prospect_id, cid, 'reponse_manuelle', json.dumps(payload, ensure_ascii=False),
             mailbox.get('id'), resp.get('message_id'),
             in_reply_to, references, 'out', parent_event_id, thread_id),
        )
        event_id = cur.lastrowid
        if thread_id is None:
            conn.execute("UPDATE prospect_events SET thread_id = id WHERE id = ?", (event_id,))
        conn.execute(
            """INSERT INTO emails_envoyes
               (lead_id, message_id_resend, date_envoi, email_destinataire,
                email_objet, email_corps, statut_envoi)
               VALUES (?, ?, datetime('now'), ?, ?, ?, 'envoye')""",
            (prospect_id, resp.get('message_id') or '', p['email'], subject, email_shell.build_html_email(subject, body)),
        )
        conn.commit()

    # Canal de contact : une réponse manuelle envoyée = moyen "mail" activé automatiquement
    prospects_repo.update_prospect(prospect_id, data_extra={'contact_mail': 1})

    return jsonify({'success': True, 'message': 'Email envoyé avec succès', 'message_id': resp.get('message_id')})


@campagnes_bp.route('/api/v2/relances/calendar', methods=['GET'])
def api_relances_calendar():
    """Projection et historique du calendrier des relances jour par jour.
    
    Calcule pour tous les prospects actifs leurs prochaines dates d'échéance en jours ouvrés réels,
    et agrège les envois passés et prévus par date et par liste/campagne.
    """
    from datetime import datetime, date, timedelta
    from core.orchestration import add_business_days, is_business_day
    from envoi import sequence_engine, template_registry

    campagne_filter = request.args.get('campagne_id', type=int)
    liste_filter = request.args.get('liste_id', type=int)
    today = date.today()
    today_str = today.strftime('%Y-%m-%d')

    NEXT_POS = {'en_sequence': 1, 'relance_1': 2, 'relance_2': 3}
    DEFAULT_DELAYS = {1: 3, 2: 7, 3: 14}

    with get_conn() as conn:
        # 1. Relances passées déjà envoyées (derniers 60 jours)
        past_sql = """
            SELECT ev.id, ev.prospect_id, ev.event_type, ev.created_at,
                   p.nom, p.prenom, p.entreprise, p.email, p.liste_id,
                   l.nom AS liste_nom, l.campagne_id, c.nom AS campagne_nom
            FROM prospect_events ev
            JOIN prospects p ON ev.prospect_id = p.id
            JOIN listes l ON p.liste_id = l.id
            JOIN campagnes c ON l.campagne_id = c.id
            WHERE ev.event_type IN ('relance_1', 'relance_2', 'relance_3')
              AND (l.type IS NULL OR l.type != 'corbeille')
        """
        past_params = []
        if campagne_filter:
            past_sql += " AND l.campagne_id = ?"
            past_params.append(campagne_filter)
        if liste_filter:
            past_sql += " AND l.id = ?"
            past_params.append(liste_filter)
        past_sql += " ORDER BY ev.created_at DESC"
        past_events = [dict(r) for r in conn.execute(past_sql, past_params).fetchall()]

        # 2. Prospects actifs en cours de séquence
        active_sql = """
            SELECT p.id, p.nom, p.prenom, p.entreprise, p.email, p.statut, p.data_extra,
                   p.liste_id, l.nom AS liste_nom, l.campagne_id, c.nom AS campagne_nom,
                   c.max_touches,
                   MAX(CASE WHEN ev.event_type IN ('initial','relance_1','relance_2','relance_3') THEN ev.created_at END) AS last_touch_at
            FROM prospects p
            JOIN listes l ON p.liste_id = l.id
            JOIN campagnes c ON l.campagne_id = c.id
            LEFT JOIN prospect_events ev ON ev.prospect_id = p.id
            WHERE p.statut IN ('en_sequence', 'relance_1', 'relance_2')
              AND p.ecarte = 0 AND p.ne_plus_contacter = 0
              AND (l.type IS NULL OR l.type != 'corbeille')
        """
        active_params = []
        if campagne_filter:
            active_sql += " AND l.campagne_id = ?"
            active_params.append(campagne_filter)
        if liste_filter:
            active_sql += " AND l.id = ?"
            active_params.append(liste_filter)
        active_sql += " GROUP BY p.id"
        active_prospects = [dict(r) for r in conn.execute(active_sql, active_params).fetchall()]

        # 3. Liste des campagnes distinctes pour les filtres
        camps = [dict(r) for r in conn.execute("SELECT id, nom, envoi_auto, validation_relances FROM campagnes WHERE statut = 'actif' ORDER BY nom ASC").fetchall()]

    # Listes distinctes visibles (filtre « Liste » du calendrier)
    listes_map = {}
    for _src in (active_prospects, past_events):
        for _r in _src:
            _id = _r.get('liste_id')
            if _id:
                listes_map[int(_id)] = _r.get('liste_nom') or f"Liste #{_id}"
    listes = [{'id': k, 'nom': v} for k, v in sorted(listes_map.items(), key=lambda kv: (kv[1] or '').lower())]

    days_data = {}

    # Insérer les événements passés
    for ev in past_events:
        d_str = (ev.get('created_at') or '')[:10]
        if not d_str:
            continue
        days_data.setdefault(d_str, {'sent': [], 'due': [], 'planned': []})
        pos = int(ev['event_type'].split('_')[-1]) if '_' in ev['event_type'] else 1
        days_data[d_str]['sent'].append({
            'prospect_id': ev['prospect_id'],
            'nom': ev['nom'],
            'prenom': ev['prenom'],
            'entreprise': ev['entreprise'],
            'email': ev['email'],
            'liste_id': ev['liste_id'],
            'liste_nom': ev['liste_nom'],
            'campagne_id': ev['campagne_id'],
            'campagne_nom': ev['campagne_nom'],
            'position': pos,
            'step_name': f"Relance {pos}",
            'status': 'sent',
            'sent_at': ev['created_at'],
            'delai_jours': None,
            'last_touch_at': None,
        })

    # Projeter les relances à venir
    for p in active_prospects:
        last_touch = p['last_touch_at']
        if not last_touch:
            continue
        try:
            last_dt = datetime.strptime(str(last_touch)[:19], '%Y-%m-%d %H:%M:%S')
        except Exception:
            continue

        current_pos = NEXT_POS.get(p['statut'], 1)
        max_touches = p.get('max_touches') or 3

        prev_dt = last_dt
        for pos in range(current_pos, max_touches):
            # Récupérer template ou délai par défaut
            t = template_registry.get_step(p['campagne_id'], position=pos)
            delai = int(t.get('delai_jours')) if t and t.get('delai_jours') is not None else DEFAULT_DELAYS.get(pos, 3)
            sched_dt = add_business_days(prev_dt, delai)
            d_str = sched_dt.strftime('%Y-%m-%d')
            sched_date = sched_dt.date()

            item = {
                'prospect_id': p['id'],
                'nom': p['nom'],
                'prenom': p['prenom'],
                'entreprise': p['entreprise'],
                'email': p['email'],
                'liste_id': p['liste_id'],
                'liste_nom': p['liste_nom'],
                'campagne_id': p['campagne_id'],
                'campagne_nom': p['campagne_nom'],
                'position': pos,
                'step_name': f"Relance {pos}",
                'delai_jours': delai,
                'last_touch_at': last_touch,
                'scheduled_date': d_str,
            }

            days_data.setdefault(d_str, {'sent': [], 'due': [], 'planned': []})
            if pos == current_pos:
                if sched_date <= today:
                    item['status'] = 'due'
                    days_data[d_str]['due'].append(item)
                else:
                    item['status'] = 'planned'
                    days_data[d_str]['planned'].append(item)
            else:
                item['status'] = 'planned'
                days_data[d_str]['planned'].append(item)
            prev_dt = sched_dt

    # Structurer par jour avec sous-groupes par liste
    result_days = {}
    total_due_count = 0
    total_sent_count = 0
    total_planned_count = 0

    for d_str, groups in days_data.items():
        try:
            day_dt = datetime.strptime(d_str, '%Y-%m-%d').date()
        except Exception:
            continue

        sent_list = groups['sent']
        due_list = groups['due']
        planned_list = groups['planned']

        total_due_count += len(due_list)
        total_sent_count += len(sent_list)
        total_planned_count += len(planned_list)

        # Agréger par lot (liste_id + position + status)
        batches = {}
        for status_key, items in [('sent', sent_list), ('due', due_list), ('planned', planned_list)]:
            for item in items:
                b_key = f"{item['liste_id']}_{item['position']}_{status_key}"
                if b_key not in batches:
                    batches[b_key] = {
                        'batch_key': b_key,
                        'liste_id': item['liste_id'],
                        'liste_nom': item['liste_nom'],
                        'campagne_id': item['campagne_id'],
                        'campagne_nom': item['campagne_nom'],
                        'position': item['position'],
                        'step_name': item['step_name'],
                        'status': status_key,
                        'count': 0,
                        'delai_jours': item.get('delai_jours'),
                        'last_touch_at': item.get('last_touch_at'),
                        'prospects': [],
                    }
                batches[b_key]['count'] += 1
                if len(batches[b_key]['prospects']) < 100:
                    batches[b_key]['prospects'].append({
                        'id': item['prospect_id'],
                        'nom': item.get('nom') or '',
                        'prenom': item.get('prenom') or '',
                        'entreprise': item.get('entreprise') or '',
                        'email': item.get('email') or '',
                    })

        result_days[d_str] = {
            'date': d_str,
            'day_of_week': day_dt.weekday(),  # 0=Lundi, 6=Dimanche
            'is_business_day': is_business_day(day_dt),
            'is_today': (d_str == today_str),
            'is_past': (day_dt < today),
            'counts': {
                'sent': len(sent_list),
                'due': len(due_list),
                'planned': len(planned_list),
                'total': len(sent_list) + len(due_list) + len(planned_list),
            },
            'batches': list(batches.values()),
        }

    return jsonify({
        'success': True,
        'today': today_str,
        'summary': {
            'total_due_now': total_due_count,
            'total_sent': total_sent_count,
            'total_planned': total_planned_count,
            'active_prospects': len(active_prospects),
        },
        'campagnes': camps,
        'listes': listes,
        'days': result_days,
    })


@campagnes_bp.route('/api/v2/relances/batch-validate', methods=['POST'])
def api_relances_batch_validate():
    """Déclenche la demande de validation Telegram immédiate pour une liste spécifique."""
    data = request.get_json(silent=True) or {}
    campagne_id = data.get('campagne_id')
    liste_id = data.get('liste_id')

    if not campagne_id or not liste_id:
        return jsonify({'success': False, 'error': 'campagne_id et liste_id requis'}), 400

    from core.relance_batch_validator import ensure_batch_requests, batch_callback
    from database.connection import get_conn

    # Réinitialise le batch s'il était complété/refusé pour permettre une nouvelle validation
    cb = batch_callback(campagne_id, liste_id)
    with get_conn() as conn:
        conn.execute("DELETE FROM relance_batches WHERE callback_id = ?", (cb,))
        conn.commit()

    res = ensure_batch_requests()
    return jsonify({'success': True, 'result': res, 'callback_id': cb})