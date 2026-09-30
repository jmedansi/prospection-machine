# -*- coding: utf-8 -*-
"""
envoi/resend_sync.py — Synchronisation du tracking de délivrabilité depuis Resend.

Pourquoi : le webhook Resend n'apparie qu'une partie des envois (plusieurs
`emails_envoyes` stockent un Message-ID RFC à la place de l'id Resend), d'où un
compteur de bounces local faussé (5 au lieu des 20 réels). L'API Resend est la
source de vérité : elle est interrogée ici pour

  1. recalculer `bounce` / `spam` / `statut_envoi` / `ouvert` / `clique`
     pour CHAQUE envoi local (appariement par id Resend, sinon par
     destinataire + date d'envoi) ;
  2. remettre à zéro les faux bounces (ex. `jmedansi@gmail.com`, marqué bounce
     par un webhook de test alors que Resend le dit `delivered`) ;
  3. alimenter `suppression_list` + `bounce_queue` → notif Telegram ✅/❌ et
     bloc « Suivi » ;
  4. ne JAMAIS régresser un état déjà positif (ouvert/cliqué restent à 1).

Planifié par `dashboard/scheduler.py` → job `resend_tracking_sync` (15 min).
Exécution manuelle : `python scripts/sync_resend_tracking.py [--dry-run]`.
"""
import logging
from collections import defaultdict

import requests

from database.connection import get_conn

logger = logging.getLogger(__name__)

_API = "https://api.resend.com/emails"
# last_event qu'on ose écrire en base (jamais `sent` : on ne régresse pas)
_APPLIED = ('bounced', 'complained', 'delivered', 'opened', 'clicked')


def _headers() -> dict:
    from config_manager import get_config
    key = get_config().get('resend_key')
    if not key:
        raise RuntimeError('RESEND_API_KEY manquante')
    return {'Authorization': f'Bearer {key}'}


def _addr(rec: dict) -> str:
    to = rec.get('to') or []
    if isinstance(to, str):
        to = [to]
    return (to[0] if to else '').strip().lower()


def fetch_all() -> list[dict]:
    """Tous les emails Resend (paginé, 100 par page).

    Deux schémas de pagination coexistent selon les versions de l'API :
    `has_more` + `after=<id>`, sinon `next_cursor`. On gère les deux.
    """
    headers = _headers()
    out: list[dict] = []
    after = cursor = None
    for _ in range(100):
        url = f'{_API}?limit=100'
        if after:
            url += f'&after={after}'
        if cursor:
            url += f'&cursor={cursor}'
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code == 401:
            raise RuntimeError('Clé API Resend sans permission lecture — '
                               'créer une clé full-access sur resend.com/api-keys')
        r.raise_for_status()
        data = r.json()
        batch = data.get('data') or []
        out.extend(batch)
        if not batch:
            break
        if 'has_more' in data:
            if not data.get('has_more'):
                break
            after = batch[-1].get('id')
            cursor = None
            if not after:
                break
        elif data.get('next_cursor'):
            cursor = data['next_cursor']
            after = None
        else:
            break
    return out


def sync(*, dry_run: bool = False, notify: bool = True, source: list[dict] | None = None) -> dict:
    """Réaligne la base sur l'API Resend. Idempotent.

    `source` : liste pré-chargée (tests / cache), sinon appel réseau.
    """
    from database import prospects as prospects_repo
    from core import bounce_handler

    remote = source if source is not None else fetch_all()
    by_id = {r['id']: r for r in remote if r.get('id')}
    groups: dict[tuple, list] = defaultdict(list)
    for r in sorted(remote, key=lambda x: x.get('created_at') or ''):
        groups[(_addr(r), (r.get('created_at') or '')[:10])].append(r)
    cursor_idx: dict[tuple, int] = defaultdict(int)
    claimed: set = set()

    def _take(key):
        lst = groups.get(key)
        if not lst:
            return None
        i = cursor_idx[key]
        while i < len(lst) and lst[i]['id'] in claimed:
            i += 1
        if i >= len(lst):
            return None
        cursor_idx[key] = i + 1
        claimed.add(lst[i]['id'])
        return lst[i]

    stats = {'remote': len(remote), 'local': 0, 'matched': 0, 'unmatched': 0,
             'updated': 0, 'bounce_marked': 0, 'bounce_cleared': 0, 'created_rows': 0,
             'queue_added': 0, 'queue_notified': 0, 'applied': dry_run}

    new_queue_ids: list[int] = []
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT id, message_id_resend, email_destinataire, date_envoi, bounce, spam "
            "FROM emails_envoyes ORDER BY id").fetchall()]
        stats['local'] = len(rows)

        for row in rows:
            rec = by_id.get(row['message_id_resend'])
            if rec is None:
                key = ((row['email_destinataire'] or '').strip().lower(),
                       (row['date_envoi'] or '')[:10])
                rec = _take(key)
            if rec is None:
                stats['unmatched'] += 1
                continue
            stats['matched'] += 1
            claimed.add(rec['id'])

            last = (rec.get('last_event') or '').lower()
            if last not in _APPLIED:
                continue

            sets, params = [], []
            if last == 'bounced':
                if not row['bounce']:
                    sets.append('bounce = 1'); stats['bounce_marked'] += 1
                sets.append('statut_envoi = ?'); params.append('bounced')
            elif last == 'complained':
                if not row['spam']:
                    sets.append('spam = 1')
                sets.append('statut_envoi = ?'); params.append('complained')
            else:
                if row['bounce']:
                    # faux bounce : Resend le dit delivered/opened/clicked
                    sets.append('bounce = 0'); stats['bounce_cleared'] += 1
                if last == 'opened':
                    sets.append('ouvert = 1')
                if last == 'clicked':
                    sets.append('clique = 1')
                sets.append('statut_envoi = ?'); params.append(last)

            if not sets:
                continue
            stats['updated'] += 1
            if not dry_run:
                conn.execute(
                    f"UPDATE emails_envoyes SET {', '.join(sets)} WHERE id = ?",
                    params + [row['id']])
        if not dry_run:
            conn.commit()

        # ── 3. Bounces Resend sans contrepartie locale → ligne de trace ──────
        # (envoi passé par Resend mais jamais journalisé localement : sans cette
        # ligne, le compteur local plafonne à 18 au lieu des 20 réels.)
        for rec in remote:
            if rec.get('id') in claimed:
                continue
            if (rec.get('last_event') or '').lower() != 'bounced':
                continue
            a = _addr(rec)
            if '@' not in a:
                continue
            if conn.execute("SELECT 1 FROM emails_envoyes WHERE message_id_resend = ?",
                            (rec['id'],)).fetchone():
                continue
            stats['bounce_marked'] += 1
            if dry_run:
                continue
            conn.execute(
                """INSERT INTO emails_envoyes
                   (lead_id, message_id_resend, date_envoi, email_destinataire, email_objet,
                    statut_envoi, bounce, notes)
                   VALUES (NULL, ?, ?, ?, ?, 'bounced', 1, 'backfill_resend_sync')""",
                (rec['id'], (rec.get('created_at') or '').replace('T', ' ')[:19],
                 a, (rec.get('subject') or '')[:300]))
            stats['created_rows'] += 1
        if not dry_run:
            conn.commit()

    # ── 4. Adresses bounce → suppression_list + bounce_queue ──────────────────
    bounced_addrs = sorted({_addr(r) for r in remote
                            if (r.get('last_event') or '').lower() == 'bounced'})
    if not dry_run:
        for addr in bounced_addrs:
            if '@' not in addr:
                continue
            prospects_repo.add_to_suppression_list(addr, 'bounce_dur')
            res = bounce_handler.record_bounce(addr, raison='bounce_dur', notify=False)
            if res.get('success') and res.get('needs_notify'):
                new_queue_ids.append(res['bounce_id'])
        stats['queue_added'] = len(new_queue_ids)
        if notify and new_queue_ids:
            stats['queue_notified'] = bounce_handler.notify_pending(new_queue_ids)

    logger.info("[resend_sync] %s", stats)
    return stats


__all__ = ["fetch_all", "sync"]
