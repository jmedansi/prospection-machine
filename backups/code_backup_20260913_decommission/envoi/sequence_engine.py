# -*- coding: utf-8 -*-
"""
envoi/sequence_engine.py — envoi d'une touche (initial ou relance) d'un prospect v2.

Chaîne complète d'une touche :
    1. verrous (objectif existant, statut attendu, écarté, opposition, email)
    2. rendu du template (position 0 = initial, position N = relance)
    3. passe d'humanisation IA (optionnelle)
    4. validation Telegram selon `objectifs.validation_telegram` :
         - 0 (auto)   → envoi direct
         - 1 (requis) → demande ✅ → attente → au clic OK le poller appelle
           approve_and_send_initial()
    5. envoi via la façade envoyer(message, boîte)
    6. succès → machine à états (qualifie→en_sequence, relance_1→relance_2, …) + event

Les relances partagent le même callback_id `v2_approve_{prospect_id}` : un reset du
pending.db est fait avant toute nouvelle demande (l'initial consommé ne bloque pas la
relance suivante). Ce module fait UN envoi (ou UNE demande), atomique.
"""
import json
import logging
from datetime import datetime

from database.connection import get_conn
from database import objectifs as objectifs_repo
from database import prospects as prospects_repo
from core.state_machine import transition_prospect
from envoi import template_registry, humanize, gateway, telegram_validation

logger = logging.getLogger(__name__)

EV_VALIDATION = 'validation_requete'

# relance : statut porteur → position du template suivant
STATUT_NEXT_POSITION = {'en_sequence': 1, 'relance_1': 2, 'relance_2': 3}
POSITION_STATUT = {1: 'relance_1', 2: 'relance_2', 3: 'relance_3'}
TOUCH_EVENT_TYPES = ('initial', 'relance_1', 'relance_2', 'relance_3')


def next_position_for(statut: str) -> int | None:
    return STATUT_NEXT_POSITION.get(statut)


def touches_count(prospect_events) -> int:
    """Nombre de touches déjà émises (initial + relances) depuis les events."""
    return sum(1 for e in prospect_events or [] if e.get('event_type') in TOUCH_EVENT_TYPES)


# ─── Préparation (verrous + rendu) ────────────────────────────────────────────

def prepare_step(objectif_id, prospect_id, position, step_label, *, expected_statut=None,
                 humanize_on=True, dry_run=False):
    """Vérifie les verrous, rend le template et (si actif) humanise.

    Retourne {'ok': bool, 'raison': str|None, 'objet', 'corps', 'preview',
              'prospect', 'objectif', 'template', 'humanise'}
    """
    obj = objectifs_repo.get_objectif(objectif_id)
    if not obj:
        return {'ok': False, 'raison': 'objectif_introuvable', 'objet': '', 'corps': ''}
    prospect = prospects_repo.get_prospect(prospect_id)
    if not prospect or prospect.get('objectif_id') != objectif_id:
        return {'ok': False, 'raison': 'prospect_introuvable', 'objet': '', 'corps': ''}
    if expected_statut and prospect.get('statut') != expected_statut:
        return {'ok': False, 'raison': 'deja_en_flux', 'objet': '', 'corps': ''}
    if prospect.get('ecarte'):
        return {'ok': False, 'raison': 'ecarte', 'objet': '', 'corps': ''}
    if prospect.get('ne_plus_contacter'):
        return {'ok': False, 'raison': 'oposition', 'objet': '', 'corps': ''}
    if not prospect.get('email'):
        return {'ok': False, 'raison': 'pas_email', 'objet': '', 'corps': ''}

    template = template_registry.get_step(objectif_id, position=position)
    if not template:
        return {'ok': False, 'raison': 'pas_template', 'objet': '', 'corps': ''}

    rendered = template_registry.render_template(template, prospect)
    objet, corps = rendered['objet'], rendered['corps']

    was_humanized = False
    if humanize_on and not dry_run:
        ctx = dict(prospect)
        ctx['_objectif'] = obj
        hum = humanize.humanize_email(objet, corps, ctx)
        objet, corps, was_humanized = hum['objet'], hum['corps'], hum['humanise']

    preview = telegram_validation.build_preview(
        obj.get('nom', ''), prospect, objet, corps,
        f'{step_label}' if not dry_run else f'{step_label.upper()} (DRY RUN)',
    )
    return {'ok': True, 'raison': None, 'objet': objet, 'corps': corps,
            'preview': preview, 'prospect': prospect, 'objectif': obj,
            'template': template, 'humanise': was_humanized}


def prepare_initial(objectif_id, prospect_id, *, humanize_on=True, dry_run=False):
    """Alias public de `prepare_step` pour la touche 0 (statut attendu : qualifie)."""
    return prepare_step(objectif_id, prospect_id, 0, 'Envoi initial',
                        expected_statut='qualifie', humanize_on=humanize_on, dry_run=dry_run)


# ─── Envoi réel (partagé) ─────────────────────────────────────────────────────

def _perform_send(objectif_id, prospect, objet, corps, *, template_id=None,
                  was_humanized=False, dry_run=False, mailbox=None,
                  expected_statut='qualifie', to_statut='en_sequence', step='initial'):
    """Envoyer via la façade + transition + event. Idempotent sur le statut attendu."""
    if prospect.get('statut') != expected_statut and not dry_run:
        return {'success': False, 'statut': 'deja_en_flux', 'message': 'statut changé', 'id': None}

    resp = gateway.envoyer({
        'to': prospect['email'],
        'nom': prospect.get('entreprise') or prospect.get('nom') or '',
        'subject': objet,
        'corps': corps,
        'objectif_id': objectif_id,
        'dry_run': dry_run,
    }, boite=mailbox)

    if not resp.get('success'):
        return {'success': False, 'statut': resp.get('statut', 'erreur_envoi'),
                'message': resp.get('erreur'), 'id': None}

    mailbox = resp.get('boite') or {}
    if dry_run:
        return {'success': True, 'statut': 'dry_run', 'step': step,
                'message': f"dry_run → {prospect['email']}", 'id': None}

    transition_prospect(prospect['id'], to_statut, reason=f'{step} envoyé')
    payload = {
        'step': step,
        'template_id': template_id,
        'humanise': was_humanized,
        'backend': mailbox.get('backend'),
        'mailbox_email': mailbox.get('email'),
    }
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO prospect_events
               (prospect_id, objectif_id, event_type, payload, mailbox_id, message_id)
               VALUES (?,?,?,?,?,?)""",
            (prospect['id'], objectif_id, step, json.dumps(payload, ensure_ascii=False),
             mailbox.get('id'), resp.get('message_id')),
        )
        conn.commit()
        event_id = cur.lastrowid
    logger.info("[sequence] %s envoyée prospect #%s objectif #%s (mailbox=%s)",
                step, prospect['id'], objectif_id, mailbox.get('email'))
    return {'success': True, 'statut': 'envoye', 'step': step,
            'message': f"envoyé → {prospect['email']}", 'id': event_id}


# ─── Demande de validation Telegram (partagée) ────────────────────────────────

def _request_validation(obj, objectif_id, prospect, objet, corps, *, step, to_statut,
                        step_label, humanise=False, template_id=None, reset=True):
    """Émet (ou réutilise) la demande ✅/❌ et journalise l'event `validation_requete`.

    `reset=True` : purge le pending.db du callback avant demande (relance après un
    initial déjà consommé). Retourne (req_success, payload_ou_erreur).
    """
    cb = telegram_validation.callback_id(prospect['id'])
    if not telegram_validation.has_requested(cb):
        if reset:
            telegram_validation.reset_for_prospect(prospect['id'])
        req = telegram_validation.request(obj, prospect, objet, corps, step_label)
        payload = {
            'step': step,
            'from_statut': prospect['statut'],
            'to_statut': to_statut,
            'callback_id': cb,
            'objet': objet,
            'corps': corps,
            'humanise': humanise,
            'template_id': template_id,
            'request_ok': req.get('success'),
        }
        with get_conn() as conn:
            conn.execute(
                """INSERT INTO prospect_events
                   (prospect_id, objectif_id, event_type, payload)
                   VALUES (?,?,?,?)""",
                (prospect['id'], objectif_id, EV_VALIDATION,
                 json.dumps(payload, ensure_ascii=False)),
            )
            conn.commit()
        return req.get('success'), payload
    return True, None


# ─── Point d'entrée public : initial ──────────────────────────────────────────

def send_initial(objectif_id, prospect_id, *, force=False, humanize_on=True,
                 dry_run=False, approval=None):
    """Envoie (ou demande la validation Telegram de) l'email initial.

    `approval` : None → suit objectifs.validation_telegram ;
                'auto' → force l'envoi direct ; 'telegram' → force la validation.
    Retour : {'success', 'statut', 'message', 'step', 'callback_id'|'id'}.
    """
    prep = prepare_initial(objectif_id, prospect_id, humanize_on=humanize_on, dry_run=dry_run)
    if not prep['ok']:
        return {'success': False, 'statut': prep['raison'], 'message': f"verrou: {prep['raison']}", 'id': None}

    prospect = prep['prospect']
    obj = prep['objectif']

    needs_tg = int(obj.get('validation_telegram') or 0) == 1
    if approval == 'auto':
        needs_tg = False
    elif approval == 'telegram':
        needs_tg = True
    if dry_run:
        needs_tg = False

    if needs_tg:
        cb = telegram_validation.callback_id(prospect['id'])
        status = telegram_validation.get_status(cb)
        if status == 'ok':
            telegram_validation.mark_completed(cb)
        elif status == 'ko':
            telegram_validation.mark_completed(cb)
            return {'success': False, 'statut': 'validation_refusee',
                    'message': 'Validation Telegram refusée', 'id': None}
        elif status == 'completed':
            return {'success': False, 'statut': 'deja_envoye',
                    'message': 'Validation déjà consommée', 'id': None}
        else:
            req_ok, _err = _request_validation(obj, objectif_id, prospect, prep['objet'],
                                               prep['corps'], step='initial',
                                               to_statut='en_sequence',
                                               step_label='Envoi initial',
                                               humanise=prep['humanise'],
                                               template_id=prep['template'].get('id'))
            if not req_ok:
                return {'success': False, 'statut': 'telegram_injoignable',
                        'message': 'Envoi Telegram impossible', 'callback_id': cb, 'id': None}
            return {'success': False, 'statut': 'attente_approbation',
                    'message': 'Validation Telegram en attente de ✅', 'callback_id': cb, 'id': None}
        return _perform_send(objectif_id, prospect, prep['objet'], prep['corps'],
                             template_id=prep['template'].get('id'),
                             was_humanized=prep['humanise'],
                             dry_run=dry_run)

    return _perform_send(objectif_id, prospect, prep['objet'], prep['corps'],
                         template_id=prep['template'].get('id'),
                         was_humanized=prep['humanise'],
                         dry_run=dry_run)


# ─── Point d'entrée public : relance ──────────────────────────────────────────

def send_relance(objectif_id, prospect_id, *, force=False, humanize_on=True,
                 dry_run=False, approval=None):
    """Envoie (ou demande la validation Telegram de) la relance suivante.

    Le statut du prospect détermine l'étape :
    en_sequence → position 1 (relance_1), relance_1 → position 2, relance_2 → position 3.
    Cycle terminé (max_touches atteint ou dernier état) → transition `sans_reponse`.
    """
    prospect = prospects_repo.get_prospect(prospect_id)
    if not prospect or prospect.get('objectif_id') != objectif_id:
        return {'success': False, 'statut': 'prospect_introuvable', 'message': 'verrou: prospect_introuvable', 'id': None}

    position = next_position_for(prospect.get('statut'))
    if position is None:
        return {'success': False, 'statut': 'pas_de_relance',
                'message': f"Aucune relance depuis {prospect.get('statut')}", 'id': None}

    obj = objectifs_repo.get_objectif(objectif_id)
    max_touches = int((obj or {}).get('max_touches') or 3) if obj else 3
    done = touches_count(prospect.get('events'))
    if done >= max_touches:
        transition_prospect(prospect_id, 'sans_reponse', reason='max_touches atteint')
        return {'success': False, 'statut': 'cycle_termine',
                'message': 'max_touches atteint — cycle fermé', 'id': None}

    prep = prepare_step(objectif_id, prospect_id, position,
                        f'Relance {position}', expected_statut=prospect.get('statut'),
                        humanize_on=humanize_on, dry_run=dry_run)
    if not prep['ok']:
        return {'success': False, 'statut': prep['raison'], 'message': f"verrou: {prep['raison']}", 'id': None}

    to_statut = POSITION_STATUT[position]
    step = f'relance_{position}'
    obj = prep['objectif']
    prospect = prep['prospect']

    needs_tg = int(obj.get('validation_telegram') or 0) == 1
    if approval == 'auto':
        needs_tg = False
    elif approval == 'telegram':
        needs_tg = True
    if dry_run:
        needs_tg = False

    if needs_tg:
        cb = telegram_validation.callback_id(prospect['id'])
        status = telegram_validation.get_status(cb)
        if status == 'ok':
            telegram_validation.mark_completed(cb)
        elif status == 'ko':
            telegram_validation.mark_completed(cb)
            return {'success': False, 'statut': 'validation_refusee',
                    'message': 'Validation Telegram refusée', 'id': None}
        elif status == 'completed':
            return {'success': False, 'statut': 'deja_envoye',
                    'message': 'Validation déjà consommée', 'id': None}
        else:
            req_ok, _err = _request_validation(obj, objectif_id, prospect, prep['objet'],
                                               prep['corps'], step=step, to_statut=to_statut,
                                               step_label=f'Relance {position}',
                                               humanise=prep['humanise'],
                                               template_id=prep['template'].get('id'))
            if not req_ok:
                return {'success': False, 'statut': 'telegram_injoignable',
                        'message': 'Envoi Telegram impossible', 'callback_id': cb, 'id': None}
            return {'success': False, 'statut': 'attente_approbation',
                    'message': 'Validation Telegram en attente de ✅', 'callback_id': cb, 'id': None}
        return _perform_send(objectif_id, prospect, prep['objet'], prep['corps'],
                             template_id=prep['template'].get('id'),
                             was_humanized=prep['humanise'],
                             dry_run=dry_run,
                             expected_statut=prospect.get('statut'), to_statut=to_statut, step=step)

    return _perform_send(objectif_id, prospect, prep['objet'], prep['corps'],
                         template_id=prep['template'].get('id'),
                         was_humanized=prep['humanise'],
                         dry_run=dry_run,
                         expected_statut=prospect.get('statut'), to_statut=to_statut, step=step)


# ─── Appelé par le poller (clic OK ✅ Telegram) ────────────────────────────────

def approve_and_send_initial(prospect_id, dry_run=False) -> dict:
    """Envoie le contenu stocké lors de la demande de validation (callback ok).

    Fonctionne pour toutes les touches (initial ou relance) : l'event
    `validation_requete` stocke step, from_statut, to_statut et le contenu.
    """
    detail = prospects_repo.get_prospect(prospect_id)
    if not detail:
        return {'success': False, 'message': 'Prospect introuvable', 'status': 'absent'}
    validation_events = [e for e in detail.get('events', []) if e.get('event_type') == EV_VALIDATION]
    if not validation_events:
        return {'success': False, 'message': 'Aucune demande de validation', 'status': 'sans_demande'}
    payload = validation_events[0].get('payload') or {}
    objet = payload.get('objet') or ''
    corps = payload.get('corps') or ''
    callback = payload.get('callback_id') or telegram_validation.callback_id(prospect_id)
    from_statut = payload.get('from_statut') or 'qualifie'
    to_statut = payload.get('to_statut') or 'en_sequence'
    step = payload.get('step') or 'initial'

    if detail.get('statut') != from_statut and not dry_run:
        return {'success': False, 'message': f'attendu {from_statut}, reçu {detail.get("statut")}',
                'status': 'deja_en_flux'}

    cb_status = telegram_validation.get_status(callback)
    if cb_status != 'ok' and not dry_run:
        return {'success': False, 'message': f"pas d'OK (status={cb_status})", 'status': cb_status or 'pending'}

    if dry_run:
        return {'success': True, 'message': f"dry_run → {detail.get('email')}", 'status': 'dry_run', 'id': None}

    telegram_validation.mark_completed(callback)
    return _perform_send(detail['objectif_id'], detail, objet, corps,
                         template_id=payload.get('template_id'),
                         was_humanized=bool(payload.get('humanise')),
                         expected_statut=from_statut, to_statut=to_statut, step=step)