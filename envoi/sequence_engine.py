# -*- coding: utf-8 -*-
"""
envoi/sequence_engine.py â€” envoi d'une touche (initial ou relance) d'un prospect v2.

ChaÃ®ne complÃ¨te d'une touche :
    1. verrous (campagne existante, statut attendu, Ã©cartÃ©, opposition, email)
    2. rendu du template (position 0 = initial, position N = relance)
    3. passe d'humanisation IA (optionnelle)
    4. validation Telegram selon `campagnes.validation_telegram` :
         - 0 (auto)   â†’ envoi direct
         - 1 (requis) â†’ demande âœ… â†’ attente â†’ au clic OK le poller appelle
           approve_and_send_initial()
    5. envoi via la faÃ§ade envoyer(message, boÃ®te)
    6. succÃ¨s â†’ machine Ã  Ã©tats (qualifieâ†’en_sequence, relance_1â†’relance_2, â€¦) + event

Les relances partagent le mÃªme callback_id `v2_approve_{prospect_id}` : un reset du
pending.db est fait avant toute nouvelle demande (l'initial consommÃ© ne bloque pas la
relance suivante). Ce module fait UN envoi (ou UNE demande), atomique.
"""
import json
import logging
from datetime import datetime

from database.connection import get_conn
from database import campagnes as campagnes_repo
from database import prospects as prospects_repo
from core.state_machine import transition_prospect
from envoi import template_registry, humanize, gateway, telegram_validation
from envoi import threading

logger = logging.getLogger(__name__)

EV_VALIDATION = 'validation_requete'

# relance : statut porteur â†’ position du template suivant
STATUT_NEXT_POSITION = {'en_sequence': 1, 'relance_1': 2, 'relance_2': 3}
POSITION_STATUT = {1: 'relance_1', 2: 'relance_2', 3: 'relance_3'}
TOUCH_EVENT_TYPES = ('initial', 'relance_1', 'relance_2', 'relance_3')


def next_position_for(statut: str) -> int | None:
    return STATUT_NEXT_POSITION.get(statut)


def touches_count(prospect_events) -> int:
    """Nombre de touches dÃ©jÃ  Ã©mises (initial + relances) depuis les events."""
    return sum(1 for e in prospect_events or [] if e.get('event_type') in TOUCH_EVENT_TYPES)


# â”€â”€â”€ PrÃ©paration (verrous + rendu) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def get_custom_step_email(prospect: dict, position: int) -> tuple[str, str] | None:
    """Retourne (objet, corps) rédigé par l'agent IA ou l'utilisateur pour ce prospect à l'étape `position`, ou None."""
    if not prospect:
        return None
    extra = prospect.get('data_extra') or {}
    if not isinstance(extra, dict):
        extra = {}

    objet = ''
    corps = ''

    if position == 0:
        objet = prospect.get('email_objet') or extra.get('email_objet') or extra.get('ia_email_objet') or ''
        corps = prospect.get('email_corps') or extra.get('email_corps') or extra.get('ia_email_corps') or ''
    elif position == 1:
        objet = extra.get('email_objet_2') or extra.get('ia_email_objet_2') or ''
        corps = extra.get('email_corps_2') or extra.get('ia_email_corps_2') or ''
    elif position == 2:
        objet = extra.get('email_objet_3') or extra.get('ia_email_objet_3') or ''
        corps = extra.get('email_corps_3') or extra.get('ia_email_corps_3') or ''
    elif position == 3:
        objet = extra.get('email_objet_4') or extra.get('ia_email_objet_4') or ''
        corps = extra.get('email_corps_4') or extra.get('ia_email_corps_4') or ''

    if corps and corps.strip():
        if not objet or not objet.strip():
            init_obj = prospect.get('email_objet') or extra.get('email_objet') or extra.get('ia_email_objet') or 'Votre activité'
            objet = threading.ensure_re(init_obj) if position > 0 else init_obj
        elif position > 0:
            objet = threading.ensure_re(objet)
        return objet.strip(), corps.strip()

    return None


# ─── Préparation (verrous + rendu) ──────────────────────────────────────────

def prepare_step(campagne_id, prospect_id, position, step_label, *, expected_statut=None,
                 humanize_on=False, dry_run=False):
    """Vérifie les verrous et extrait le contenu de l'email.
    
    Source de vérité absolue : L'email rédigé pour le prospect (agent IA / utilisateur).
    Repli : Le template de la campagne si aucun email personnalisé n'est présent.

    Retourne {'ok': bool, 'raison': str|None, 'objet', 'corps', 'preview',
              'prospect', 'campagne', 'template', 'humanise'}
    """
    obj = campagnes_repo.get_campagne(campagne_id)
    if not obj:
        return {'ok': False, 'raison': 'campagne_introuvable', 'objet': '', 'corps': ''}
    prospect = prospects_repo.get_prospect(prospect_id)
    if not prospect or prospect.get('campagne_id') != campagne_id:
        return {'ok': False, 'raison': 'prospect_introuvable', 'objet': '', 'corps': ''}
    prospect['_campagne'] = obj
    if expected_statut and prospect.get('statut') != expected_statut:
        return {'ok': False, 'raison': 'deja_en_flux', 'objet': '', 'corps': ''}
    if prospect.get('ecarte'):
        return {'ok': False, 'raison': 'ecarte', 'objet': '', 'corps': ''}
    if prospect.get('ne_plus_contacter'):
        return {'ok': False, 'raison': 'oposition', 'objet': '', 'corps': ''}
    if not prospect.get('email'):
        return {'ok': False, 'raison': 'pas_email', 'objet': '', 'corps': ''}

    # 1. Vérifier en priorité si un email rédigé existe pour ce prospect
    custom = get_custom_step_email(prospect, position)
    template = None
    if custom:
        objet, corps = custom
    else:
        # 2. Repli template de séquence si aucun email personnalisé n'existe
        template = template_registry.get_step(campagne_id, position=position)
        if not template:
            return {'ok': False, 'raison': 'pas_template', 'objet': '', 'corps': ''}
        rendered = template_registry.render_template(template, prospect)
        objet, corps = rendered['objet'], rendered['corps']
        if position > 0:
            objet = threading.ensure_re(objet)

    preview = telegram_validation.build_preview(
        obj.get('nom', ''), prospect, objet, corps,
        f'{step_label}' if not dry_run else f'{step_label.upper()} (DRY RUN)',
    )
    return {'ok': True, 'raison': None, 'objet': objet, 'corps': corps,
            'preview': preview, 'prospect': prospect, 'campagne': obj,
            'template': template, 'humanise': False}


def prepare_initial(campagne_id, prospect_id, *, humanize_on=False, dry_run=False):
    """Alias public de `prepare_step` pour la touche 0 (statut attendu : qualifie)."""
    return prepare_step(campagne_id, prospect_id, 0, 'Envoi initial',
                        expected_statut='qualifie', humanize_on=humanize_on, dry_run=dry_run)


# â”€â”€â”€ Envoi rÃ©el (partagÃ©) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _perform_send(campagne_id, prospect, objet, corps, *, template_id=None,
                  was_humanized=False, dry_run=False, mailbox=None,
                  expected_statut='qualifie', to_statut='en_sequence', step='initial'):
    """Envoyer via la faÃ§ade + transition + event. Idempotent sur le statut attendu."""
    if prospect.get('statut') != expected_statut and not dry_run:
        return {'success': False, 'statut': 'deja_en_flux', 'message': 'statut changÃ©', 'id': None}

    # ── Threading RFC 2822 : fil de conversation dans prospect_events ──────────
    prior = threading.last_touch_event(prospect.get('events'))
    if prior and prior.get('message_id'):
        in_reply_to = prior.get('message_id')
        references = threading.extend_references(prior.get('references_header'),
                                                 prior.get('message_id'))
        parent_event_id = prior.get('id')
        thread_id = prior.get('thread_id') or prior.get('id')
    else:
        in_reply_to = references = parent_event_id = thread_id = None

    resp = gateway.envoyer({
        'to': prospect['email'],
        'nom': prospect.get('entreprise') or prospect.get('nom') or '',
        'subject': objet,
        'corps': corps,
        'campagne_id': campagne_id,
        'dry_run': dry_run,
        'message_id': None,
        'in_reply_to': in_reply_to,
        'references': references,
    }, boite=mailbox)

    if not resp.get('success'):
        return {'success': False, 'statut': resp.get('statut', 'erreur_envoi'),
                'message': resp.get('erreur'), 'id': None}

    mailbox = resp.get('boite') or {}
    if dry_run:
        return {'success': True, 'statut': 'dry_run', 'step': step,
                'message': f"dry_run â†’ {prospect['email']}", 'id': None}

    transition_prospect(prospect['id'], to_statut, reason=f'{step} envoyÃ©')
    payload = {
        'step': step,
        'template_id': template_id,
        'humanise': was_humanized,
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
            (prospect['id'], campagne_id, step, json.dumps(payload, ensure_ascii=False),
             mailbox.get('id'), resp.get('message_id'),
             in_reply_to, references, 'out', parent_event_id, thread_id),
        )
        event_id = cur.lastrowid
        if thread_id is None:
            # l'event racine du fil est la premiÃ¨re touche elle-mÃªme
            conn.execute("UPDATE prospect_events SET thread_id = id WHERE id = ?", (event_id,))
        # ── Pont tracking : une ligne emails_envoyes par touche (webhook + polling Resend)
        conn.execute(
            """INSERT INTO emails_envoyes
               (lead_id, message_id_resend, message_id_brevo, date_envoi,
                email_destinataire, email_objet, email_corps, statut_envoi)
               VALUES (?,?,?,datetime('now'),?,?,?,'envoye')""",
            (prospect['id'],
             resp.get('resend_id') or resp.get('message_id') or None,
             resp.get('message_id') or None,
             prospect.get('email') or '',
             objet, corps),
        )
        conn.commit()
    logger.info("[sequence] %s envoyÃ©e prospect #%s objectif #%s (mailbox=%s, message_id=%s)",
                step, prospect['id'], campagne_id, mailbox.get('email'), resp.get('message_id'))
    return {'success': True, 'statut': 'envoye', 'step': step,
            'message': f"envoyÃ© â†’ {prospect['email']}", 'id': event_id}


# â”€â”€â”€ Demande de validation Telegram (partagÃ©e) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _request_validation(obj, campagne_id, prospect, objet, corps, *, step, to_statut,
                        step_label, humanise=False, template_id=None, reset=True):
    """Ã‰met (ou rÃ©utilise) la demande âœ…/âŒ et journalise l'event `validation_requete`.

    `reset=True` : purge le pending.db du callback avant demande (relance aprÃ¨s un
    initial dÃ©jÃ  consommÃ©). Retourne (req_success, payload_ou_erreur).
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
                   (prospect_id, campagne_id, event_type, payload)
                   VALUES (?,?,?,?)""",
                (prospect['id'], campagne_id, EV_VALIDATION,
                 json.dumps(payload, ensure_ascii=False)),
            )
            conn.commit()
        return req.get('success'), payload
    return True, None


# â”€â”€â”€ Point d'entrÃ©e public : initial â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def send_initial(campagne_id, prospect_id, *, force=False, humanize_on=True,
                 dry_run=False, approval=None):
    """Envoie (ou demande la validation Telegram de) l'email initial.

    `approval` : None â†’ suit objectifs.validation_telegram ;
                'auto' â†’ force l'envoi direct ; 'telegram' â†’ force la validation.
    Retour : {'success', 'statut', 'message', 'step', 'callback_id'|'id'}.
    """
    prep = prepare_initial(campagne_id, prospect_id, humanize_on=humanize_on, dry_run=dry_run)
    if not prep['ok']:
        return {'success': False, 'statut': prep['raison'], 'message': f"verrou: {prep['raison']}", 'id': None}

    prospect = prep['prospect']
    obj = prep['campagne']

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
                    'message': 'Validation Telegram refusÃ©e', 'id': None}
        elif status == 'completed':
            return {'success': False, 'statut': 'deja_envoye',
                    'message': 'Validation dÃ©jÃ  consommÃ©e', 'id': None}
        else:
            req_ok, _err = _request_validation(obj, campagne_id, prospect, prep['objet'],
                                               prep['corps'], step='initial',
                                               to_statut='en_sequence',
                                               step_label='Envoi initial',
                                               humanise=prep['humanise'],
                                               template_id=prep['template'].get('id'))
            if not req_ok:
                return {'success': False, 'statut': 'telegram_injoignable',
                        'message': 'Envoi Telegram impossible', 'callback_id': cb, 'id': None}
            return {'success': False, 'statut': 'attente_approbation',
                    'message': 'Validation Telegram en attente de âœ…', 'callback_id': cb, 'id': None}
        return _perform_send(campagne_id, prospect, prep['objet'], prep['corps'],
                             template_id=prep['template'].get('id'),
                             was_humanized=prep['humanise'],
                             dry_run=dry_run)

    return _perform_send(campagne_id, prospect, prep['objet'], prep['corps'],
                         template_id=prep['template'].get('id'),
                         was_humanized=prep['humanise'],
                         dry_run=dry_run)


# â”€â”€â”€ Point d'entrÃ©e public : relance â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def send_relance(campagne_id, prospect_id, *, force=False, humanize_on=True,
                 dry_run=False, approval=None):
    """Envoie (ou demande la validation Telegram de) la relance suivante.

    Le statut du prospect dÃ©termine l'Ã©tape :
    en_sequence â†’ position 1 (relance_1), relance_1 â†’ position 2, relance_2 â†’ position 3.
    Cycle terminÃ© (max_touches atteint ou dernier Ã©tat) â†’ transition `sans_reponse`.
    """
    prospect = prospects_repo.get_prospect(prospect_id)
    if not prospect or prospect.get('campagne_id') != campagne_id:
        return {'success': False, 'statut': 'prospect_introuvable', 'message': 'verrou: prospect_introuvable', 'id': None}

    position = next_position_for(prospect.get('statut'))
    if position is None:
        return {'success': False, 'statut': 'pas_de_relance',
                'message': f"Aucune relance depuis {prospect.get('statut')}", 'id': None}

    obj = campagnes_repo.get_campagne(campagne_id)
    max_touches = int((obj or {}).get('max_touches') or 3) if obj else 3
    done = touches_count(prospect.get('events'))
    if done >= max_touches:
        transition_prospect(prospect_id, 'sans_reponse', reason='max_touches atteint')
        return {'success': False, 'statut': 'cycle_termine',
                'message': 'max_touches atteint â€” cycle fermÃ©', 'id': None}

    prep = prepare_step(campagne_id, prospect_id, position,
                        f'Relance {position}', expected_statut=prospect.get('statut'),
                        humanize_on=humanize_on, dry_run=dry_run)
    if not prep['ok']:
        return {'success': False, 'statut': prep['raison'], 'message': f"verrou: {prep['raison']}", 'id': None}
    # Threading : une relance reprend le fil → objet préfixé "Re:"
    prep['objet'] = threading.ensure_re(prep['objet'])

    to_statut = POSITION_STATUT[position]
    step = f'relance_{position}'
    obj = prep['campagne']
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
                    'message': 'Validation Telegram refusÃ©e', 'id': None}
        elif status == 'completed':
            return {'success': False, 'statut': 'deja_envoye',
                    'message': 'Validation dÃ©jÃ  consommÃ©e', 'id': None}
        else:
            req_ok, _err = _request_validation(obj, campagne_id, prospect, prep['objet'],
                                               prep['corps'], step=step, to_statut=to_statut,
                                               step_label=f'Relance {position}',
                                               humanise=prep['humanise'],
                                               template_id=prep['template'].get('id'))
            if not req_ok:
                return {'success': False, 'statut': 'telegram_injoignable',
                        'message': 'Envoi Telegram impossible', 'callback_id': cb, 'id': None}
            return {'success': False, 'statut': 'attente_approbation',
                    'message': 'Validation Telegram en attente de âœ…', 'callback_id': cb, 'id': None}
        return _perform_send(campagne_id, prospect, prep['objet'], prep['corps'],
                             template_id=prep['template'].get('id'),
                             was_humanized=prep['humanise'],
                             dry_run=dry_run,
                             expected_statut=prospect.get('statut'), to_statut=to_statut, step=step)

    return _perform_send(campagne_id, prospect, prep['objet'], prep['corps'],
                         template_id=prep['template'].get('id'),
                         was_humanized=prep['humanise'],
                         dry_run=dry_run,
                         expected_statut=prospect.get('statut'), to_statut=to_statut, step=step)


# â”€â”€â”€ AppelÃ© par le poller (clic OK âœ… Telegram) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def approve_and_send_initial(prospect_id, dry_run=False) -> dict:
    """Envoie le contenu stockÃ© lors de la demande de validation (callback ok).

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
        return {'success': False, 'message': f'attendu {from_statut}, reÃ§u {detail.get("statut")}',
                'status': 'deja_en_flux'}

    cb_status = telegram_validation.get_status(callback)
    if cb_status != 'ok' and not dry_run:
        return {'success': False, 'message': f"pas d'OK (status={cb_status})", 'status': cb_status or 'pending'}

    if dry_run:
        return {'success': True, 'message': f"dry_run â†’ {detail.get('email')}", 'status': 'dry_run', 'id': None}

    telegram_validation.mark_completed(callback)
    return _perform_send(detail['campagne_id'], detail, objet, corps,
                         template_id=payload.get('template_id'),
                         was_humanized=bool(payload.get('humanise')),
                         expected_statut=from_statut, to_statut=to_statut, step=step)