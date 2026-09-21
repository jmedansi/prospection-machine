# -*- coding: utf-8 -*-
"""
envoi/reply_poller.py — détection des réponses entrantes (IMAP) pour le modèle v2.

Chaque boîte `mailboxes` disposant de creds IMAP (imap_host/imap_user/imap_pass)
peut être pollée. Un email UNSEEN est classé :
  - 'ndr'          (bounce / rebond)                    → event `ndr`, AUCUNE transition
  - 'auto_reply'   (répondeur OOO / noreply)            → event `auto_reply`, AUCUNE transition
  - 'reponse'      (réponse réelle d'un prospect)       → transition a_traiter_humain
                                                          + event `reponse`
Règle spec §2 : toute réponse suspend IMMÉDIATEMENT les relances automatiques
(après A↔a_traiter_humain, `relances_due()` ne sélectionne plus le prospect).

Matching prospect :
  1) prioritaire : References / In-Reply-To référençant un `message_id` stocké dans
     `prospect_events` (résolution précise, disponible avec Resend ou des envois
     SMTP qui posent un header Message-ID) ;
  2) sinon : adresse From == `prospects.email`, statut dans l'ensemble "déjà séquencé"
     (le prospect a donc reçu un email de notre boîte) — l'email est reçu dans la
     boîte pollée, donc le destinataire est bien l'une de nos boîtes.

Idempotence : chaque email UNSEEN traité est marqué SEEN (impossible de le re-traiter
au run suivant). Un run traite une fois chaque message (set en mémoire).
"""
import imaplib
import logging
import re
from datetime import datetime, timedelta

from email import message_from_bytes, policy
from email.header import decode_header
from email.utils import parseaddr, parsedate_to_datetime

from database.connection import get_conn
from database import prospects_repo
from core.state_machine import transition_prospect, REPLY_STATUTS

logger = logging.getLogger(__name__)

EV_REPONSE = 'reponse'
KINDS = ('reponse', 'ndr', 'auto_reply')

# ─── Réseaux de marqueurs ──────────────────────────────────────────────────────

# premiers "atomes" des adresses expéditrices typiques des rebonds
NDR_FROM_HINTS = (
    'mailer-daemon', 'postmaster', 'mdaemon', 'mta', 'administrator', 'system',
    'avast', 'norton', 'kaspersky', 'spam', 'abuse',
)
# atomes des répondeurs automatiques / notifications
AUTO_FROM_HINTS = (
    'noreply', 'no-reply', 'no_reply', 'norepons', 'donotreply', 'do-notreply',
    'do_not_reply', 'auto-reply', 'autoreply', 'auto', 'bot', 'robot', 'support',
    'helpdesk', 'informations', 'notification', 'notifications', 'account', 'billing',
)
NDR_SUBJECT_RE = re.compile(
    r'(undeliver|delivery\s+(status|failure|problem|report)|returned\s+mail|'
    r'non[- ]?delivery|failure\s+notice|n?dr\b|mail\s+(delivery\s+)?(failed|failure)|'
    r'bounce|removed\s+by\s+(antivirus|filter)|recipient\s+unknown)',
    re.IGNORECASE)
AUTO_SUBJECT_RE = re.compile(
    r'(out[- ]?of[- ]?office|o\.?o\.?o\.?|\bouo\b|automatic\s+reply|auto[- ]?r[ée]ponse'
    r'|vacation|absen[ct]e|absence|notice\s+of\s+absence|r[ée]ponse\s+automatique)',
    re.IGNORECASE)

SENT_STATUTS = ('en_sequence', 'relance_1', 'relance_2', 'relance_3', 'sans_reponse',
                'a_traiter_humain', 'rdv_obtenu', 'pas_interesse', 'a_relancer_plus_tard')
SENT_CLAUSE = "(" + ",".join(f"'{s}'" for s in SENT_STATUTS) + ")"


def _first_atom(addr: str) -> str:
    return (addr or '').split('@')[0].strip().lower()


def _decoded(value) -> str:
    """Décode un header mail (RFC2047) en texte simple."""
    if not value:
        return ''
    out = []
    for part, enc in decode_header(value):
        try:
            if isinstance(part, bytes):
                part = part.decode(enc or 'utf-8', errors='replace')
        except Exception:
            part = str(part)
        out.append(str(part))
    return ''.join(out)


# ─── Parsing / classification ─────────────────────────────────────────────────

def parse_reply(raw: bytes) -> dict:
    """Parse des octets bruts d'un email → dict de champs utilisables.

    Contrat de sortie :
    {from_addr, from_name, subject, date_iso, message_id, in_reply_to,
     references, body, content_type, raw}
    """
    msg = message_from_bytes(raw, policy=policy.default)
    name, addr = parseaddr(msg.get('From', ''))
    body = _body_text(msg)
    return {
        'from_addr': (addr or '').strip().lower(),
        'from_name': _decoded(name or msg.get('From', '')),
        'subject': _decoded(msg.get('Subject', '')),
        'date_iso': _header_date(msg),
        'message_id': (msg.get('Message-ID') or '').strip(),
        'in_reply_to': (msg.get('In-Reply-To') or '').strip(),
        'references': (msg.get('References') or '').strip(),
        'body': body,
        'content_type': (msg.get_content_type() or ''),
        'raw': raw,
    }


def _body_text(msg) -> str:
    if msg.is_multipart():
        parts = [p for p in msg.walk()]
        for p in parts:
            if p.get_content_type() == 'text/plain':
                return p.get_content() or ''
            if p.get_content_type() in ('message/delivery-status', 'message/disposition-notification'):
                return p.get_payload() or ''
        for p in parts:
            if p.get_content_type() == 'text/html':
                return re.sub(r'<[^>]+>', ' ', p.get_content() or '')
        return ''
    return msg.get_content() or ''


def _header_date(msg) -> str:
    try:
        dt = parsedate_to_datetime(msg.get('Date', ''))
        if dt:
            return dt.isoformat(timespec='seconds')
    except Exception:
        pass
    return ''


def classify(parsed: dict) -> str:
    """Classifie un email reçu en 'ndr' | 'auto_reply' | 'reponse'."""
    addr = parsed.get('from_addr') or ''
    atom = _first_atom(addr)
    subject = parsed.get('subject') or ''
    ctype = parsed.get('content_type') or ''

    if atom.startswith(NDR_FROM_HINTS):
        return 'ndr'
    if ctype == 'message/delivery-status' or ctype == 'multipart/report':
        # NDR standard (ex. DSN/notifications de livraison)
        return 'ndr'
    if NDR_SUBJECT_RE.search(subject):
        return 'ndr'
    if AUTO_FROM_HINTS and atom.startswith(AUTO_FROM_HINTS):
        return 'auto_reply'
    if AUTO_SUBJECT_RE.search(subject):
        return 'auto_reply'
    return 'reponse'


# ─── Matching prospect ─────────────────────────────────────────────────────────

def match_events_message_ids(message_ids: list) -> list:
    """prospect_events dont le message_id correspond à des References reçues."""
    ids = [m for m in message_ids if m]
    if not ids:
        return []
    placeholders = ','.join('?' for _ in ids)
    with get_conn() as conn:
        rows = conn.execute(
            f"""SELECT prospect_id, objectif_id FROM prospect_events
                WHERE message_id IS NOT NULL AND message_id != ''
                  AND message_id IN ({placeholders})
                ORDER BY id DESC""",
            ids,
        ).fetchall()
    return [dict(r) for r in rows]


def match_prospect(parsed: dict) -> dict | None:
    """Trouve le prospect concerné par une réponse (voir docstring module)."""
    references = re.split(r'\s+', ' '.join([parsed.get('in_reply_to') or '',
                                            parsed.get('references') or '']).strip())
    hits = match_events_message_ids(references)
    if hits:
        from database import prospects_repo
        hit = hits[0]
        p = prospects_repo.get_prospect(hit['prospect_id'])
        if p:
            return p

    from_addr = parsed.get('from_addr') or ''
    if not from_addr:
        return None
    with get_conn() as conn:
        row = conn.execute(
            f"""SELECT id, objectif_id, statut FROM prospects
                WHERE LOWER(email) = ? AND statut IN {SENT_CLAUSE}
                  AND ecarte = 0 AND ne_plus_contacter = 0
                ORDER BY updated_at DESC LIMIT 1""",
            (from_addr,),
        ).fetchone()
    return dict(row) if row else None


# ─── Réponse → file humaine ────────────────────────────────────────────────────

def handle_reply(parsed: dict, prospect: dict, kind: str = 'reponse',
                 mailbox_email: str = '') -> dict:
    """Applique une réponse : transition a_traiter_humain (reponse) + event.

    `ndr` / `auto_reply` → event uniquement (aucune transition).
    Retourne {'success', 'statut', 'prospect_id', 'event_id', 'transition'}.
    """
    if kind not in KINDS:
        kind = 'reponse'
    pid = prospect['id']
    oid = prospect.get('objectif_id')
    snippet = re.sub(r'\s+', ' ', (parsed.get('body') or '')).strip()[:220]

    transition = None
    if kind == 'reponse':
        current = prospects_repo.get_prospect(pid)
        if current and current.get('statut') not in REPLY_STATUTS:
            transition = transition_prospect(pid, 'a_traiter_humain',
                                             reason='réponse entrante (IMAP)')

    payload = {
        'kind': kind,
        'from_addr': parsed.get('from_addr') or '',
        'from_name': parsed.get('from_name') or '',
        'subject': parsed.get('subject') or '',
        'date': parsed.get('date_iso') or '',
        'message_id': parsed.get('message_id') or '',
        'snippet': snippet,
        'mailbox_email': mailbox_email,
    }
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO prospect_events
               (prospect_id, objectif_id, event_type, payload, message_id)
               VALUES (?,?,?,?,?)""",
            (pid, oid, kind, __import__('json').dumps(payload, ensure_ascii=False),
             parsed.get('message_id') or None),
        )
        conn.commit()
        event_id = cur.lastrowid
    if kind == 'reponse':
        _notify_reponse(prospect, parsed, snippet)
    logger.info("[replies] %s prospect #%s objectif #%s (%s → %s)",
                kind, pid, oid, parsed.get('from_addr') or '?',
                (transition or {}).get('statut', 'pas de transition'))
    return {'success': True, 'statut': 'ok', 'prospect_id': pid,
            'event_id': event_id, 'transition': not transition is None}


def _notify_reponse(prospect: dict, parsed: dict, snippet: str = '') -> None:
    """Notification Telegram dès qu'un prospect répond (jamais bloquant)."""
    try:
        from envoi.telegram_validation import notify_answer
        notify_answer(prospect, subject=parsed.get('subject') or '',
                      snippet=snippet or parsed.get('body') or '')
    except Exception:
        logger.exception('[replies] notification Telegram échouée')


# ─── Poll IMAP ─────────────────────────────────────────────────────────────────

def _open_imap(mailbox: dict):
    """Ouvre une connexion IMAP SSL sur la boîte (None si pas de creds)."""
    host = (mailbox.get('imap_host') or '').strip()
    user = (mailbox.get('imap_user') or '').strip()
    pwd = (mailbox.get('imap_pass') or '').strip()
    if not (host and user and pwd):
        return None
    cli = imaplib.IMAP4_SSL(host, 993)
    cli.login(user, pwd)
    cli.select('INBOX')
    return cli


def poll_mailbox(mailbox: dict, lookback_hours: int = 48) -> dict:
    """Poll un INBOX : classifie, matche et traite les réponses UNSEEN.

    Retourne un résumé {'success', 'mailbox', 'skipped'|'scanned', compteurs}.
    """
    summary = {'success': False, 'mailbox': mailbox.get('email') or mailbox.get('label'),
               'scanned': 0, 'ndr': 0, 'auto_reply': 0, 'reponse': 0,
               'no_match': 0, 'transitions': 0, 'errors': []}
    cli = _open_imap(mailbox)
    if cli is None:
        summary['skipped'] = 'pas de creds IMAP'
        return summary
    try:
        since = (datetime.now() - timedelta(hours=lookback_hours)).strftime('%d-%b-%Y')
        typ, data = cli.search(None, 'UNSEEN', f'SINCE {since}')
        ids = (data[0] or b'').split()
        summary['scanned'] = len(ids)
        processed = set()
        for msg_id in ids:
            try:
                typ, items = cli.fetch(msg_id, '(RFC822)')
                raw = None
                for it in items:
                    if isinstance(it, tuple):
                        raw = it[1]
                        break
                if not raw:
                    continue
                parsed = parse_reply(raw)
                key = parsed.get('message_id') or parsed.get('from_addr')
                if key in processed:
                    continue
                processed.add(key)
                kind = classify(parsed)
                if kind == 'reponse':
                    prospect = match_prospect(parsed)
                    if not prospect:
                        summary['no_match'] += 1
                        cli.store(msg_id, '+FLAGS', r'(\Seen)')
                        continue
                    res = handle_reply(parsed, prospect, 'reponse',
                                       mailbox_email=(mailbox.get('imap_user') or mailbox.get('email')))
                    summary['reponse'] += 1
                    if res.get('transition'):
                        summary['transitions'] += 1
                else:
                    summary[kind] += 1
                cli.store(msg_id, '+FLAGS', r'(\Seen)')
                summary['success'] = True
            except Exception as e:
                logger.error("[replies] erreur traitement msg %s: %s", msg_id, e)
                summary['errors'].append(str(e))
        return summary
    except Exception as e:
        summary['errors'].append(str(e))
        logger.error("[replies] erreur poll mailbox %s: %s", mailbox.get('email'), e)
        return summary
    finally:
        try:
            cli.logout()
        except Exception:
            pass


def run_poll(lookback_hours: int = 48) -> dict:
    """Poll toutes les boîtes actives disposant de creds IMAP."""
    with get_conn() as conn:
        boxes = conn.execute(
            "SELECT * FROM mailboxes WHERE actif = 1 ORDER BY id"
        ).fetchall()
    box_summaries = []
    for box in boxes:
        box_summaries.append(poll_mailbox(dict(box), lookback_hours=lookback_hours))
    scan = sum(s.get('scanned', 0) for s in box_summaries)
    rep = sum(s.get('reponse', 0) for s in box_summaries)
    return {'success': True, 'summary': box_summaries,
            'total_scanned': scan, 'total_reponses': rep,
            'errors': [e for s in box_summaries for e in s.get('errors', [])]}