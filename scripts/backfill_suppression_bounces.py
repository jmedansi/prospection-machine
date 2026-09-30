#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Alimente `suppression_list` avec les adresses qui ont rebondi chez Resend.

Pourquoi ce script
------------------
La base locale ne connaît que 5 des 20 bounces réels : `webhooks.py` apparie les
événements sur l'id Resend, or 191/295 lignes d'`emails_envoyes` stockent un
Message-ID RFC à la place → le webhook ne les trouve jamais. L'API Resend est
donc la seule source de vérité exploitable.

Le script est idempotent (`INSERT OR IGNORE`) et dry-run par défaut.

Usage
-----
    python scripts/backfill_suppression_bounces.py             # apercu
    python scripts/backfill_suppression_bounces.py --apply     # ecrit en base
    python scripts/backfill_suppression_bounces.py --apply --ref <email>
                                                                # retire une adresse
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

API = 'https://api.resend.com/emails'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')


def load_key() -> str | None:
    k = os.getenv('RESEND_API_KEY')
    if k:
        return k.strip()
    env = os.path.join(ROOT, '.env')
    if os.path.exists(env):
        for line in open(env, encoding='utf-8', errors='replace'):
            if line.strip().startswith('RESEND_API_KEY='):
                v = line.split('=', 1)[1].strip().strip('"').strip("'")
                if v:
                    return v
    return None


def api(key: str, path: str):
    req = urllib.request.Request(
        'https://api.resend.com' + path,
        headers={'Authorization': 'Bearer ' + key,
                 'Accept': 'application/json', 'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, {'error': e.read().decode('utf-8', 'replace')[:300]}


def fetch_bounced(key: str) -> list[dict]:
    """Tous les emails dont `last_event == 'bounced'` (pagination)."""
    out, after, pages = [], None, 0
    while pages < 50:
        st, d = api(key, '/emails?limit=100' + (f'&after={after}' if after else ''))
        if st != 200:
            raise SystemExit('API Resend HTTP %s : %s' % (st, d))
        batch = d.get('data') or []
        out += [e for e in batch if e.get('last_event') == 'bounced']
        pages += 1
        if len(batch) < 100 or d.get('has_more') is False:
            break
        after = batch[-1].get('id')
        if not after:
            break
    return out


def address_of(e: dict) -> str:
    to = e.get('to') or []
    if isinstance(to, str):
        to = [to]
    a = (to[0] if to else '').strip().lower()
    return a


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--apply', action='store_true',
                    help='ecrit en base (sinon apercu seul)')
    ap.add_argument('--ref', metavar='EMAIL',
                    help='retire cette adresse de la suppression_list')
    args = ap.parse_args()

    from database.connection import get_conn

    if args.ref:
        with get_conn() as conn:
            cur = conn.execute("DELETE FROM suppression_list WHERE lower(email) = ?",
                               (args.ref.strip().lower(),))
            conn.commit()
        print('%s → %d ligne(s) supprimee(s)' % (args.ref, cur.rowcount))
        return

    key = load_key()
    if not key:
        raise SystemExit('RESEND_API_KEY introuvable (variable ou .env)')

    bounced = fetch_bounced(key)
    addrs = sorted({a for a in (address_of(e) for e in bounced) if '@' in a})

    print('=' * 70)
    print('Bounces Resend          : %d emails' % len(bounced))
    print('Adresses distinctes     : %d' % len(addrs))
    print('=' * 70)

    with get_conn() as conn:
        deja = {r['email'] for r in conn.execute(
            "SELECT lower(email) AS email FROM suppression_list").fetchall()}
        candidats = [a for a in addrs if a not in deja]
        conn.commit()

    deja_chez_nous = sorted(set(addrs) & deja)
    print('\nDeja en suppression_list (%d) : %s' % (len(deja_chez_nous),
                                                   ', '.join(deja_chez_nous) or '-'))
    print('\nA ajouter (%d) :' % len(candidats))
    for a in candidats:
        n = sum(1 for e in bounced if address_of(e) == a)
        print('   %-40s bounce x%d' % (a, n))

    if not candidats:
        print('\nRien a faire : suppression_list deja a jour.')
        return

    if not args.apply:
        print("\nDRY-RUN — relancer avec --apply pour ecrire %d entree(s)."
              % len(candidats))
        return

    from database import prospects as prospects_repo
    ok = sum(1 for a in candidats
             if prospects_repo.add_to_suppression_list(a, 'bounce_dur'))
    print('\n%d entree(s) inscrite(s) dans suppression_list (raison=bounce_dur).' % ok)

    with get_conn() as conn:
        n = conn.execute("SELECT COUNT(*) FROM suppression_list").fetchone()[0]
    print('suppression_list : %d entrees au total.' % n)


if __name__ == '__main__':
    main()
