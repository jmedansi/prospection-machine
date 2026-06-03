# -*- coding: utf-8 -*-
"""
Enrichissement de rattrapage pour les leads précédemment marqués comme 'introuvables'
ou en 'timeout' sur les mentions légales.
"""
import sqlite3
import sys
import os
import argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from enrichisseur.mentions_legales_enricher import enrichir_lead, _format_notes, update_db

def get_failed_leads(limit=50):
    with sqlite3.connect('data/prospection.db') as conn:
        conn.row_factory = sqlite3.Row
        sql = """
            SELECT id, nom, site_web, source, secteur
            FROM leads_bruts
            WHERE site_web IS NOT NULL AND site_web != ''
              AND (
                  notes LIKE '%(mentions legales introuvables)%'
                  OR notes LIKE '%(timeout mentions legales)%'
              )
            ORDER BY id DESC
            LIMIT ?
        """
        rows = conn.execute(sql, (limit,)).fetchall()
        return [dict(r) for r in rows]

def main(limit=50):
    leads = get_failed_leads(limit)
    total = len(leads)
    if total == 0:
        print("No failed leads found to retry.")
        return

    print(f"[...] Lancement du rattrapage d'enrichissement sur {total} leads 'introuvables'...\n")
    ok = 0
    skip = 0

    for i, lead in enumerate(leads, 1):
        lid = lead["id"]
        nom = lead["nom"] or "(sans nom)"
        url = lead["site_web"]
        
        print(f"[{i:3d}/{total}] #{lid:5d} {nom[:35]:35s} | {url[:40]:40s}", end=" ", flush=True)

        try:
            result = enrichir_lead(lid, url, nom)
            notes = _format_notes(result)
            
            if notes:
                update_db(lid, notes, result)
                dirigeant = f"{result['dirigeant_prenom'] or ''} {result['dirigeant_nom'] or ''}".strip()
                emails = ", ".join(result["emails"][:1]) if result["emails"] else ""
                print(f"[OK] TROUVE: {dirigeant[:20]} | {emails[:25]}")
                ok += 1
            else:
                # Sauvegarde en mentions_introuvables pour exclure des prochains retry
                update_db(lid, "mentions_introuvables", result)
                print("[SKIP] Toujours rien")
                skip += 1
        except Exception as e:
            print(f"[ERR] Erreur: {str(e)}")
            skip += 1

    print(f"\n==========================================")
    print(f"Rattrapage terminé.")
    print(f"  - Récupérés avec succès: {ok}/{total} ({round(ok/total*100)}%)")
    print(f"  - Échecs persistants   : {skip}/{total}")
    print(f"==========================================")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rattrapage d'enrichissement ML")
    parser.add_argument("--limit", type=int, default=50, help="Nombre maximal de leads à retraiter")
    args = parser.parse_args()
    main(limit=args.limit)
