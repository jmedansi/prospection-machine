#!/usr/bin/env python
"""Small helper: republish up to N reports sequentially to validate reporter stability.
"""
import os
import sys
# Ensure project root is on sys.path when invoked from tools/ directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.connection import get_conn
from reporter.main import republish_from_db
from time import sleep


def main(limit=3):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT la.lead_id, lb.nom FROM leads_audites la
            JOIN leads_bruts lb ON la.lead_id = lb.id
            WHERE (la.lien_rapport IS NULL OR la.lien_rapport = '')
            AND la.statut = 'audite'
            ORDER BY la.id
            LIMIT ?
            """,
            (limit,)
        ).fetchall()

    print(f"Will republish {len(rows)} leads")
    for r in rows:
        d = dict(r)
        lead_id = d.get('lead_id')
        nom = d.get('nom')
        print(f"Republishing {nom} ({lead_id})")
        try:
            url = republish_from_db(lead_id=lead_id)
            print(" ->", url)
        except Exception as e:
            print("Error during republish:", e)
        sleep(1)


if __name__ == '__main__':
    main(3)
