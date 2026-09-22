# -*- coding: utf-8 -*-
"""
scripts/backfill_emails_envoyes.py — Reconstruit le pont de tracking emails_envoyes.

Contexte : les envois initiaux/relances (liste 155 / campagne 44, 2026-09-21) ont été
journalisés dans `prospect_events` (event_type initial/relance_k, payload + message_id
RFC), mais le « pont tracking » (ligne emails_envoyes par touche) n'existait pas encore
dans le code en cours d'exécution. Ce script reconstruit ces lignes a posteriori.

Règles :
  - une ligne emails_envoyes par event sortant `initial`/`relance_1..3` ;
  - `date_envoi` = created_at de l'event (horodatage réel) ;
  - `message_id_brevo` = message_id RFC de l'event (payload.rfc_message_id sinon
    event.message_id) ; `message_id_resend` = idem (aucun resend_id historisé) ;
  - `email_objet`/`email_corps` = payload.objet/corps (repli data_extra du prospect) ;
  - idempotent : jamais de doublon (dédupe sur message_id_brevo / lead_id+date_envoi,
    ignore les lignes de test pré-existantes).

Usage :
  python scripts/backfill_emails_envoyes.py --campagne 44        # tout (recommandé)
  python scripts/backfill_emails_envoyes.py --liste 155
  python scripts/backfill_emails_envoyes.py --prospect 8839
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from database.connection import get_conn

OUT_EVENTS = ('initial', 'relance_1', 'relance_2', 'relance_3')


def _payload(row) -> dict:
    try:
        return json.loads(row['payload']) if row['payload'] else {}
    except Exception:
        return {}


def _extra(prospect) -> dict:
    try:
        return json.loads(prospect['data_extra']) if prospect['data_extra'] else {}
    except Exception:
        return {}


def _prospect_rows(conn, campagne_id=None, liste_id=None, prospect_id=None):
    sql = """SELECT p.id, p.email, p.data_extra, p.liste_id
             FROM prospects p
             JOIN listes l ON p.liste_id = l.id
             WHERE 1=1"""
    params = []
    if prospect_id is not None:
        sql += " AND p.id = ?"
        params.append(int(prospect_id))
    elif liste_id is not None:
        sql += " AND l.id = ?"
        params.append(int(liste_id))
    elif campagne_id is not None:
        sql += " AND l.campagne_id = ?"
        params.append(int(campagne_id))
    else:
        raise SystemExit("Spécifier --campagne, --liste ou --prospect")
    return conn.execute(sql + " ORDER BY p.id", params).fetchall()


def _event_rows(conn, prospect_id):
    sql = ("SELECT event_type, created_at, message_id, payload FROM prospect_events "
           "WHERE prospect_id = ? AND direction = 'out' AND event_type IN "
           "({ph}) ORDER BY created_at ASC".format(ph=",".join("?" * len(OUT_EVENTS))))
    return conn.execute(sql, (int(prospect_id), *OUT_EVENTS)).fetchall()


def main():
    ap = argparse.ArgumentParser(description="Backfill emails_envoyes depuis prospect_events")
    ap.add_argument('--campagne', type=int, default=None)
    ap.add_argument('--liste', type=int, default=None)
    ap.add_argument('--prospect', type=int, default=None)
    ap.add_argument('--dry-run', action='store_true', help="affiche sans insérer")
    args = ap.parse_args()

    inserted = 0
    skipped_existing = 0
    no_message_id = 0
    with get_conn() as conn:
        prospects = _prospect_rows(conn, args.campagne, args.liste, args.prospect)
        for p in prospects:
            extra = _extra(p)
            for ev in _event_rows(conn, p['id']):
                pay = _payload(ev)
                rfc = pay.get('rfc_message_id') or ev['message_id'] or None
                if not rfc:
                    no_message_id += 1
                    continue
                objet = pay.get('objet') or extra.get('email_objet') or ''
                corps = pay.get('corps') or extra.get('email_corps') or ''
                # Dédupe : déjà présent via message_id_brevo (lignes existantes si incluse)
                dup = conn.execute(
                    "SELECT 1 FROM emails_envoyes WHERE message_id_brevo IS NOT NULL "
                    "AND message_id_brevo = ?", (rfc,)
                ).fetchone()
                if dup:
                    skipped_existing += 1
                    continue
                # Dédupe complémentaire : même lead + même date (tests sans RFC dans la col.)
                dup2 = conn.execute(
                    "SELECT 1 FROM emails_envoyes WHERE lead_id = ? AND date_envoi = ? "
                    "AND email_objet = ?", (p['id'], ev['created_at'], objet)
                ).fetchone()
                if dup2:
                    skipped_existing += 1
                    continue
                if args.dry_run:
                    print(f"[dry-run] + emails_envoyes lead={p['id']} "
                          f"{ev['event_type']} {ev['created_at']} rfc={rfc[:40]}")
                    inserted += 1
                    continue
                conn.execute(
                    """INSERT INTO emails_envoyes
                       (lead_id, message_id_brevo, message_id_resend, date_envoi,
                        email_destinataire, email_objet, email_corps, statut_envoi)
                       VALUES (?,?,?,?,?,?,?,'envoye')""",
                    (p['id'], rfc, rfc, ev['created_at'],
                     p['email'] or '', objet, corps),
                )
                inserted += 1
                print(f"[ok] + emails_envoyes lead={p['id']} {ev['event_type']} "
                      f"{ev['created_at']} rfc={rfc[:40]}")
    print(f"\nRésumé : {inserted} ligne(s) insérée(s), {skipped_existing} doublon(s) "
          f"ignoré(s) ({no_message_id} event(s) sans message_id)")


if __name__ == '__main__':
    main()