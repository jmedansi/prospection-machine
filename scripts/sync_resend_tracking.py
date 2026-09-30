#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Réaligne le tracking de délivrabilité local sur l'API Resend.

Pourquoi
-------
Le webhook Resend n'apparie qu'une partie des envois (plusieurs lignes
d'`emails_envoyes` stockent un Message-ID RFC au lieu de l'id Resend) : la base
locale ne comptait que 5 bounces sur 20 réels, et `jmedansi@gmail.com` était
faussement marqué bounce. Ce script (idempotent) :

  1. recalcule `bounce` / `spam` / `statut_envoi` / `ouvert` / `clique`
     pour chaque envoi, en appariant par id Resend puis par destinataire+date ;
  2. remet à zéro les faux bounces ;
  3. alimente `suppression_list` + `bounce_queue` → notif Telegram / bloc Suivi.

Usage
-----
    python scripts/sync_resend_tracking.py                # apercu (dry-run)
    python scripts/sync_resend_tracking.py --apply        # ecrit en base
    python scripts/sync_resend_tracking.py --apply --no-notify
                                                          # sans Telegram
    python scripts/sync_resend_tracking.py --apply --source <json>
                                                          # sans appel reseau
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--apply', action='store_true',
                    help='ecrit en base (sinon apercu seul)')
    ap.add_argument('--no-notify', action='store_true',
                    help="n'envoie pas les notifications Telegram")
    ap.add_argument('--source', metavar='JSON',
                    help='fichier JSON Resend deja telecharge (pas d appel reseau)')
    args = ap.parse_args()

    from envoi import resend_sync

    source = None
    if args.source:
        with open(args.source, encoding='utf-8') as fh:
            data = json.load(fh)
        source = data if isinstance(data, list) else data.get('data') or []
        print('Source locale : %d email(s) depuis %s' % (len(source), args.source))

    try:
        res = resend_sync.sync(dry_run=not args.apply, notify=not args.no_notify,
                               source=source)
    except Exception as e:
        raise SystemExit('Echec de la synchro : %s' % e)

    print('=' * 70)
    print('remote=%(remote)d  local=%(local)d  apparie=%(matched)d  '
          'non-apparie=%(unmatched)d' % res)
    print('maj=%(updated)d  bounce_poses=%(bounce_marked)d  '
          'faux_bounce_corriges=%(bounce_cleared)d' % res)
    if args.apply:
        print('bounce_queue : %(queue_added)d nouvelle(s) ligne(s), '
              '%(queue_notified)d notification(s) Telegram' % res)
    else:
        print('DRY-RUN — relancer avec --apply pour ecrire.')
    print('=' * 70)

    from database.connection import get_conn
    with get_conn() as conn:
        b = conn.execute('SELECT COUNT(*) c FROM emails_envoyes WHERE bounce=1').fetchone()['c']
        s = conn.execute('SELECT COUNT(*) c FROM suppression_list').fetchone()['c']
        q = conn.execute("SELECT COUNT(*) c FROM bounce_queue WHERE statut='pending'").fetchone()['c']
        t = conn.execute('SELECT COUNT(*) c FROM emails_envoyes').fetchone()['c']
    print('emails_envoyes : %d lignes, %d bounce(s) | suppression_list : %d | '
          'bounce_queue en attente : %d' % (t, b, s, q))


if __name__ == '__main__':
    main()
