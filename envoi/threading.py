# -*- coding: utf-8 -*-
"""
envoi/threading.py — construction du threading RFC 2822 (v2).

Helpers pures pour bâtir les headers In-Reply-To / References et préfixer
l'objet d'une relance avec "Re:". Le fil vit dans `prospect_events`
(direction 'out' = touches sortantes, 'in' = réponses entrantes), voir
`database/schema.migrate_emails_threading()`.
"""
import re

_RE_PREFIX = re.compile(r'^(re|fw|fwd|tr)\s*:\s*', re.IGNORECASE)

TOUCH_EVENT_TYPES = ('initial', 'relance_1', 'relance_2', 'relance_3')


def ensure_re(subject: str) -> str:
    """Préfixe l'objet par 'Re: ' s'il n'en porte pas déjà un (re/fw/fwd/tr)."""
    subject = (subject or '').strip()
    if not subject or _RE_PREFIX.match(subject):
        return subject
    return f'Re: {subject}'


def extend_references(prior_references, prior_message_id) -> str:
    """Header References = références du message parent + son Message-ID.

    Conforme RFC 2822 §3.6.4 : chaque message porte l'historique complet
    (ancêtres + message immédiatement précédent), espaces séparés.
    """
    parts = []
    if prior_references:
        parts.extend(str(prior_references).split())
    if prior_message_id:
        mid = str(prior_message_id).strip()
        if mid and mid not in parts:
            parts.append(mid)
    return ' '.join(parts)


def last_touch_event(events, touch_types=TOUCH_EVENT_TYPES):
    """Dernier event de touche sortante (le plus récent). None si absent.

    `events` est la liste des events d'un prospect (prospects_repo.get_prospect
    les ordonne par created_at DESC).
    """
    for ev in events or []:
        if ev.get('event_type') in touch_types:
            return ev
    return None