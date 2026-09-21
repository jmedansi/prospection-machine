# -*- coding: utf-8 -*-
"""
envoi/gateway.py — façade d'envoi UNIQUE : envoyer(message, boîte)

Découple le transport (SMTP Zoho, Resend) de l'appelant. L'appelant ne parle
jamais à smtp_sender / resend_sender directement : il appelle `envoyer()`, la
façade choisit la boîte (rotation + quota + pool objectif + backend_pref) et
dispatche.

Contrat de retour (identique aux senders) :
    {'success': bool, 'statut': str, 'message_id': str|None,
     'erreur': str|None, 'boite': dict|None}

Ne touche NI à suppression_list NI à la machine à états : c'est le pipeline
qui enregistre les events prospect_events.
"""
import json
import logging

from database.connection import get_conn

logger = logging.getLogger(__name__)

BACKENDS = ('smtp', 'resend')


def get_next_mailbox(objectif_id=None, backend_pref='auto'):
    """Sélectionne la prochaine boîte éligible.

    Critères :
      - actif = 1 et usage_jour < quota_jour
      - si objectif_id et objectif_pool != '*' → l'objectif doit être dans le pool
      - backend_pref ('smtp' | 'resend' | 'auto') filtre les boîtes
    Retourne le row dict de la boîte (avec clé 'id') ou None.
    """
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM mailboxes").fetchall()

    if not rows:
        # table mailboxes vraiment vide : seeder une boîte depuis .env
        seeded = _seed_default_mailbox_from_env()
        if seeded:
            rows = [seeded]
        else:
            return None

    candidates = []
    for r in rows:
        m = dict(r) if not isinstance(r, dict) else dict(r)
        if not m.get('actif'):
            continue
        if (m.get('usage_jour') or 0) >= (m.get('quota_jour') or 0):
            continue
        pool = (m.get('objectif_pool') or '*').strip()
        if pool != '*':
            try:
                eligible = json.loads(pool)
            except Exception:
                eligible = []
            if objectif_id is not None and objectif_id not in eligible:
                continue
        if backend_pref in BACKENDS and m.get('backend') != backend_pref:
            continue
        candidates.append(m)

    if not candidates:
        return None
    candidates.sort(key=lambda m: m['usage_jour'])
    return candidates[0]


def _seed_default_mailbox_from_env():
    import os
    from core.config import ensure_env
    ensure_env()
    host = os.getenv('SMTP_HOST', '').strip() or os.getenv('IMAP_HOST', '').strip()
    user = os.getenv('SMTP_USER', '').strip() or os.getenv('IMAP_USER', '').strip()
    email = os.getenv('SMTP_FROM_EMAIL', '').strip() or user
    if not (host and user):
        return None
    domain = host.split('.')[-2] if '.' in host else host
    port = int(os.getenv('SMTP_PORT', '465').strip() or 465)
    smtp_pass = os.getenv('SMTP_PASSWORD', '').strip() or os.getenv('IMAP_PASSWORD', '').strip()
    try:
        with get_conn() as conn:
            existing = conn.execute("SELECT * FROM mailboxes WHERE email = ?", (email,)).fetchone()
            if existing:
                return dict(existing)
            conn.execute(
                """INSERT INTO mailboxes
                   (label, domaine, email, smtp_host, smtp_port, smtp_user, smtp_pass,
                    imap_host, imap_user, imap_pass, backend, quota_jour, usage_jour)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'smtp', 40, 0)""",
                ('Boîte par défaut (.env)', domain, email, host, port, user, smtp_pass,
                 os.getenv('IMAP_HOST', '').strip(), os.getenv('IMAP_USER', '').strip(),
                 os.getenv('IMAP_PASSWORD', '').strip()),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM mailboxes WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None
    except Exception as e:
        logger.error("[gateway] seed mailboxes: %s", e)
        return None


def _mark_sent(mailbox_id, usage=1):
    if not mailbox_id:
        return
    try:
        with get_conn() as conn:
            conn.execute(
                "UPDATE mailboxes SET usage_jour = usage_jour + ?, last_send_at = datetime('now') WHERE id = ?",
                (usage, mailbox_id),
            )
            conn.commit()
    except Exception:
        pass


def envoyer(message: dict, boite=None) -> dict:
    """Envoie UN message via la façade transport.

    `message` (dict) — clés attendues :
        to, nom (prospect), subject (objet), corps (HTML ou texte),
        lien_rapport (optional), dry_run (bool),
        objectif_id (optional, pour sélection de boîte / pool / backend_pref).
    `boite` : dict de la table mailboxes (retour de get_next_mailbox) ou None
              → sélection automatique (rotation + quota + pool).

    Retour : contrat commun + 'boite'.
    """
    to = message.get('to') or message.get('email') or ''
    to_str = ', '.join([t.strip() for t in str(to).split(',') if t.strip()])
    if not to_str:
        return {'success': False, 'statut': 'erreur_config', 'message_id': None,
                'erreur': 'Aucun destinataire', 'boite': None}

    backend_pref = 'auto'
    objectif_id = message.get('objectif_id')
    if objectif_id is not None:
        try:
            from database import objectifs as objectifs_repo
            o = objectifs_repo.get_objectif(int(objectif_id))
            backend_pref = (o or {}).get('backend_pref') or 'auto'
        except Exception:
            pass

    mailbox = boite
    dry_run = bool(message.get('dry_run'))
    if mailbox is None:
        mailbox = get_next_mailbox(objectif_id=objectif_id, backend_pref=backend_pref)
    if mailbox is None and not dry_run:
        return {'success': False, 'statut': 'erreur_config', 'message_id': None,
                'erreur': 'Aucune boîte éligible (quota épuisé ou pool vide)', 'boite': None}

    resp = _dispatch(mailbox, to_str, message)
    if resp.get('success') and not dry_run and mailbox:
        _mark_sent(mailbox.get('id'))
    resp['boite'] = mailbox
    return resp


def _dispatch(mailbox, to_str, message):
    from envoi import smtp_sender
    from envoi import resend_sender

    nom = message.get('nom') or ''
    subject = message.get('subject') or message.get('objet') or ''
    corps = message.get('corps') or message.get('html') or ''
    lien_rapport = message.get('lien_rapport')
    dry_run = bool(message.get('dry_run'))

    backend = ((mailbox or {}).get('backend') or 'smtp') if mailbox else 'smtp'

    if backend == 'resend' and mailbox:
        return resend_sender.send_prospecting_email(
            prospect_email=to_str, prospect_nom=nom,
            email_objet=subject, email_corps=corps,
            lien_rapport=lien_rapport, dry_run=dry_run,
        )

    if mailbox:
        port = int(mailbox.get('smtp_port') or 0)
        if port == 465:
            use_ssl, use_tls = True, False
        elif port == 587:
            use_ssl, use_tls = False, True
        else:
            use_ssl = use_tls = None
        return smtp_sender.send_prospecting_email_smtp(
            prospect_email=to_str, prospect_nom=nom,
            email_objet=subject, email_corps=corps,
            lien_rapport=lien_rapport, dry_run=dry_run,
            host=mailbox.get('smtp_host') or None,
            port=port if port else None,
            user=mailbox.get('smtp_user') or None,
            password=mailbox.get('smtp_pass') or None,
            use_ssl=use_ssl,
            use_tls=use_tls,
            from_email=mailbox.get('email') or None,
            from_name=mailbox.get('label') or None,
        )

    return smtp_sender.send_prospecting_email_smtp(
        prospect_email=to_str, prospect_nom=nom,
        email_objet=subject, email_corps=corps,
        lien_rapport=lien_rapport, dry_run=dry_run,
    )