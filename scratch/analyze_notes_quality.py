# -*- coding: utf-8 -*-
"""
Analyse la qualité de l'extraction des responsables ML.
"""
import sqlite3
import re

def main():
    conn = sqlite3.connect('data/prospection.db')
    conn.row_factory = sqlite3.Row

    # Stats globales
    total = conn.execute("SELECT COUNT(*) FROM leads_bruts").fetchone()[0]
    total_with_site = conn.execute("SELECT COUNT(*) FROM leads_bruts WHERE site_web IS NOT NULL AND site_web != ''").fetchone()[0]
    notes_vides    = conn.execute("SELECT COUNT(*) FROM leads_bruts WHERE notes IS NULL OR notes = ''").fetchone()[0]
    introuvables   = conn.execute("SELECT COUNT(*) FROM leads_bruts WHERE notes LIKE '%(mentions legales introuvables)%' OR notes LIKE '%(timeout mentions legales)%'").fetchone()[0]
    notes_ok       = conn.execute("""
        SELECT COUNT(*) FROM leads_bruts 
        WHERE notes IS NOT NULL AND notes != '' 
          AND notes NOT LIKE '%(mentions legales introuvables)%'
          AND notes NOT LIKE '%(timeout mentions legales)%'
          AND notes NOT LIKE '%(rien trouve sur mentions legales)%'
    """).fetchone()[0]
    avec_email_in_notes = conn.execute("SELECT COUNT(*) FROM leads_bruts WHERE notes LIKE '%Email:%'").fetchone()[0]
    avec_dirigeant       = conn.execute("SELECT COUNT(*) FROM leads_bruts WHERE notes LIKE '%Dirigeant:%'").fetchone()[0]
    avec_responsable     = conn.execute("""
        SELECT COUNT(*) FROM leads_bruts 
        WHERE notes LIKE '%Responsable%' OR notes LIKE '%Directeur%' OR notes LIKE '%G\xe9rant%' OR notes LIKE '%President%'
    """).fetchone()[0]

    print("=== ANALYSE QUALITE EXTRACTION MENTIONS LEGALES ===\n")
    print(f"Total leads en base           : {total}")
    print(f"Leads avec site web           : {total_with_site}")
    print(f"Notes vides (pas encore traité): {notes_vides}")
    print(f"ML introuvables / timeout     : {introuvables}")
    print(f"ML avec info trouvée          : {notes_ok} ({'%.0f' % (notes_ok/total_with_site*100)}% des sites)")
    print(f"  dont avec email trouvé      : {avec_email_in_notes}")
    print(f"  dont avec Dirigeant nommé   : {avec_dirigeant}")
    print(f"  dont avec Responsable/Dir.  : {avec_responsable}")

    # Analyse des patterns de notes "réussies"
    print("\n=== EXEMPLES DE BONNES EXTRACTIONS (top 10) ===")
    bons = conn.execute("""
        SELECT id, nom, site_web, email, notes, source, secteur
        FROM leads_bruts
        WHERE notes IS NOT NULL AND notes != ''
          AND notes NOT LIKE '%(mentions legales introuvables)%'
          AND notes NOT LIKE '%(timeout mentions legales)%'
          AND notes NOT LIKE '%(rien trouve sur mentions legales)%'
          AND (notes LIKE '%Dirigeant%' OR notes LIKE '%Responsable%' OR notes LIKE '%Directeur%' OR notes LIKE '%Gérant%')
        ORDER BY id DESC
        LIMIT 10
    """).fetchall()
    for r in bons:
        print(f"\n  #{r['id']} | {r['nom']} | {r['secteur']} | source={r['source']}")
        print(f"  Site: {r['site_web']}")
        for line in r['notes'].split('\n'):
            if line.strip():
                print(f"    -> {line.strip()}")

    # Chercher des cas suspects (nom inventé ou format bizarre)
    print("\n=== CAS ATYPIQUES (email dans notes mais pas dans email) ===")
    suspects = conn.execute("""
        SELECT id, nom, email, notes
        FROM leads_bruts
        WHERE notes LIKE '%Email:%'
          AND (email IS NULL OR email = '')
        ORDER BY id DESC
        LIMIT 5
    """).fetchall()
    for r in suspects:
        print(f"\n  #{r['id']} | {r['nom']} | email DB vide")
        for line in r['notes'].split('\n'):
            if line.strip():
                print(f"    → {line.strip()}")

    conn.close()

if __name__ == "__main__":
    main()
