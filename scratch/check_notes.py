# -*- coding: utf-8 -*-
import sqlite3

def main():
    conn = sqlite3.connect('data/prospection.db')
    conn.row_factory = sqlite3.Row

    # 1. Leads récents avec notes non vides
    print("=== Leads récents avec notes (mentions légales) ===\n")
    rows = conn.execute("""
        SELECT id, nom, site_web, email, source, secteur, notes, date_scraping
        FROM leads_bruts
        WHERE notes IS NOT NULL AND notes != ''
        ORDER BY id DESC
        LIMIT 20
    """).fetchall()
    
    for r in rows:
        print(f"ID: {r['id']} | {r['nom']} | {r['source']} | {r['secteur']}")
        print(f"  Site: {r['site_web']}")
        print(f"  Email: {r['email']}")
        print(f"  Notes: {r['notes'][:300]}")
        print()

    # 2. Stats globales
    total = conn.execute("SELECT COUNT(*) FROM leads_bruts").fetchone()[0]
    with_notes = conn.execute("SELECT COUNT(*) FROM leads_bruts WHERE notes IS NOT NULL AND notes != ''").fetchone()[0]
    with_email = conn.execute("SELECT COUNT(*) FROM leads_bruts WHERE email IS NOT NULL AND email != ''").fetchone()[0]
    print(f"=== Stats ===")
    print(f"Total leads: {total}")
    print(f"Avec notes (responsable ML): {with_notes} ({round(with_notes/total*100)}%)")
    print(f"Avec email: {with_email} ({round(with_email/total*100)}%)")
    
    # 3. Leads sans email mais avec notes (les plus exploitables)
    print("\n=== Leads sans email mais avec notes (à enrichir) ===")
    rows2 = conn.execute("""
        SELECT id, nom, site_web, source, secteur, notes
        FROM leads_bruts
        WHERE (email IS NULL OR email = '')
          AND notes IS NOT NULL AND notes != ''
        ORDER BY id DESC
        LIMIT 10
    """).fetchall()
    for r in rows2:
        print(f"  ID: {r['id']} | {r['nom']} | {r['secteur']}")
        print(f"    Notes: {r['notes'][:200]}")
        print()

    conn.close()

if __name__ == "__main__":
    main()
