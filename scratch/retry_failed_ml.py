# -*- coding: utf-8 -*-
import sqlite3
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from enrichisseur.mentions_legales_enricher import enrichir_lead, _format_notes

def main():
    conn = sqlite3.connect('data/prospection.db')
    conn.row_factory = sqlite3.Row

    # Sélectionner des leads Maps ou Ads qui ont 'mentions legales introuvables'
    rows = conn.execute("""
        SELECT id, nom, site_web, source, secteur
        FROM leads_bruts
        WHERE notes LIKE '%(mentions legales introuvables)%'
           OR notes = 'mentions_introuvables'
        ORDER BY id DESC
        LIMIT 10
    """).fetchall()

    if not rows:
        print("Aucun lead marqué comme 'introuvable' n'a été trouvé dans la base.")
        conn.close()
        return

    print(f"=== RETRY ENRICHISSEMENT SUR {len(rows)} LEADS MARQUES INTROUVABLES ===\n")
    
    ok = 0
    for r in rows:
        lid = r['id']
        nom = r['nom']
        url = r['site_web']
        source = r['source']
        
        print(f"#{lid} | {nom[:30]} | URL: {url} | Source: {source}")
        print("  Running enrichir_lead...")
        
        try:
            result = enrichir_lead(lid, url, nom)
            notes = _format_notes(result)
            if notes:
                print(f"  [SUCCES] Infos trouvées : {notes}")
                ok += 1
            else:
                print("  [ECHEC] Toujours rien trouvé.")
        except Exception as e:
            print(f"  [ERREUR] Exception lors de l'appel : {e}")
        print("-" * 50)

    print(f"\nTotal retentés : {len(rows)} | Succès : {ok} ({round(ok/len(rows)*100)}%)")
    conn.close()

if __name__ == "__main__":
    main()
