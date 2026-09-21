#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
scripts/create_edutrack_lists.py — Créer des listes EduTrack par catégorie A/B/C

Parse Liste_ecole.txt, importe les écoles dans leads_bruts (pays='bj', secteur='ecole',
source='edutrack_manual'), puis crée des listes de 10 leads par catégorie.

Usage:
    python scripts/create_edutrack_lists.py
    python scripts/create_edutrack_lists.py --batch-size 10
    python scripts/create_edutrack_lists.py --dry-run
    python scripts/create_edutrack_lists.py --reset
"""

import sys
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from database.connection import get_conn

EDUTRACK_FILE = os.path.join(ROOT, "Listes_contacts_edutrack", "Liste_ecole.txt")

SECTEUR = "ecole"
SOURCE = "edutrack_manual"
PAYS = "bj"

CATEGORY_META = {
    "A": {"label": "Haut Standing / Écoles d'élite", "icone": "\U0001F3EB", "couleur": "#8b5cf6"},
    "B": {"label": "Standing Moyen-Supérieur", "icone": "\U0001F4DA", "couleur": "#3b82f6"},
    "C": {"label": "Potentiel Élevé de Friction", "icone": "\U0001F3AF", "couleur": "#ef4444"},
}


def parse_schools(filepath):
    """Parse Liste_ecole.txt -> list of dicts with all school data."""
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.read().split("\n")

    schools = []
    current_cat = None
    school_start = None

    def finish_school(end):
        nonlocal school_start
        if school_start is not None:
            block = lines[school_start:end]
            school = extract_school(block, current_cat)
            if school:
                schools.append(school)
            school_start = None

    for i, line in enumerate(lines):
        s = line.strip()

        m = re.match(r'^#{3,4}\s*CAT[ÉE]GORIE\s+(A|B|C)\b', s, re.IGNORECASE)
        if m:
            finish_school(i)
            current_cat = m.group(1).upper()
            continue

        if re.match(r'^\s*\d+\.\s+\S', line):
            finish_school(i)
            school_start = i

    finish_school(len(lines))
    return schools


def extract_school(lines, category):
    """Extract school data from a block of lines."""
    raw = "\n".join(lines)
    first = lines[0].strip()

    m = re.match(r'(\d+)\.\s+(.+?)(?:\s*[\u2014\u2013\-]\s*(.+))?$', first)
    if not m:
        return None

    num = m.group(1)
    name = m.group(2).strip() if m.group(2) else ""
    location = m.group(3).strip() if m.group(3) else ""

    interpeller = _find(raw, r'- Interpeller\s*:\s*(.+?)(?:\n|$)')
    contact_raw = _find(raw, r'- Contact\s*:\s*((?:(?!\n\s*-|\n\s*\n).)*)', flags=re.DOTALL)
    base = _find(raw, r'- Base officielle\s*:\s*(.+?)(?:\n|$)')
    base_loc = _find(raw, r'Localisation\s*:\s*(.+?)(?:\n|$)')
    base_cycle = _find(raw, r'Cycle\s*:\s*(.+?)(?:\n|$)')
    fondateur = _find(raw, r'- Fondateur/Propriétaire\s*:\s*(.+?)(?:\n|$)')
    tel_fondateur = _find(raw, r'Tél\.?\s*Fondateur\s*:\s*(.+?)(?:\n|$)')
    directeur = _find(raw, r'- Directeur\s*:\s*(.+?)(?:\n|$)')
    tel_directeur = _find(raw, r'Tél\.?\s*Directeur\s*:\s*(.+?)(?:\n|$)')

    contact_phones = _extract_phones(contact_raw) if contact_raw else []

    # Fallback: schools without "- Contact :" — scan header only
    if not contact_phones:
        header = raw
        for skip in ["Base officielle", "Fondateur/Propri\u00e9taire", "Directeur"]:
            idx = header.find(f"- {skip}")
            if idx >= 0:
                header = header[:idx]
        contact_phones = _extract_phones(header)

    parts = [f"#{num}"]
    parts.append(f"\u00c9cole: {name}")
    if location:
        parts.append(f"Ville: {location}")
    if interpeller:
        parts.append(f"Interpeller: {interpeller}")
    if contact_phones:
        parts.append(f"Contact: {' | '.join(contact_phones)}")

    if base:
        parts.append("")
        parts.append(f"Base: {base}")
        if base_loc:
            parts.append(f"Localisation: {base_loc}")
        if base_cycle:
            parts.append(f"Cycle: {base_cycle}")

    if fondateur:
        parts.append("")
        parts.append(f"Fondateur: {fondateur}")
        if tel_fondateur:
            parts.append(f"T\u00e9l. Fondateur: {tel_fondateur}")

    if directeur:
        parts.append("")
        parts.append(f"Directeur: {directeur}")
        if tel_directeur:
            parts.append(f"T\u00e9l. Directeur: {tel_directeur}")

    notes = "\n".join(parts)

    telephone = contact_phones[0] if contact_phones else None
    if telephone:
        telephone = telephone.replace(" ", "").replace("(", "").replace(")", "").replace("*", "")

    return {
        "num": int(num),
        "nom": name,
        "ville": location if location else None,
        "telephone": telephone,
        "category": category or "C",
        "notes": notes,
    }


def _extract_phones(text):
    """Extract all phone numbers from text (handles multi-line phone blocks)."""
    phones = []
    for m in re.finditer(r'\(?\+229\)?[ \d\(\)]{6,}', text):
        phone = m.group().strip().rstrip("*)")
        phone = phone.replace("*", "").strip()
        if phone not in phones:
            phones.append(phone)
    for m in re.finditer(r'(?<!\d)(\d{2}\s\d{2}[\s\d]{4,})', text):
        phone = m.group().strip()
        if phone and phone not in phones and re.search(r'\d{8,}', phone):
            phones.append(phone)
    return phones


def _find(text, pattern, group=1, flags=0):
    m = re.search(pattern, text, flags)
    return m.group(group).strip() if m else None


def insert_lead(conn, school):
    """Insert a school into leads_bruts if not duplicate by (nom, telephone, source)."""
    existing = conn.execute(
        "SELECT id FROM leads_bruts WHERE nom = ? AND telephone = ? AND source = ?",
        (school["nom"], school["telephone"] or "", SOURCE)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE leads_bruts SET notes = ?, ville = ? WHERE id = ?",
            (school["notes"], school["ville"], existing["id"])
        )
        return existing["id"]

    cur = conn.execute(
        """INSERT INTO leads_bruts
           (nom, ville, telephone, secteur, source, pays, notes, statut)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'en_attente')""",
        (school["nom"], school["ville"], school["telephone"],
         SECTEUR, SOURCE, PAYS, school["notes"])
    )
    return cur.lastrowid


def create_lists(conn, schools, batch_size=10, dry_run=False):
    """Create lead_lists by category, 10 per batch."""
    by_cat = {}
    for s in schools:
        by_cat.setdefault(s["category"], []).append(s)

    created = []

    for cat in sorted(by_cat.keys()):
        leads = by_cat[cat]
        meta = CATEGORY_META.get(cat, {})
        label = meta.get("label", f"Catégorie {cat}")
        icone = meta.get("icone", "\U0001F4CB")
        couleur = meta.get("couleur", "#6366f1")

        for batch_idx in range(0, len(leads), batch_size):
            batch = leads[batch_idx:batch_idx + batch_size]
            batch_num = batch_idx // batch_size + 1
            total_batches = (len(leads) + batch_size - 1) // batch_size

            list_name = f"Edu_{cat}{batch_num}_10_leads"

            if total_batches > 1:
                desc = f"Catégorie {cat} \u2014 {label} \u2014 {len(batch)} écoles (Bénin, lot {batch_num}/{total_batches})"
            else:
                desc = f"Catégorie {cat} \u2014 {label} \u2014 {len(batch)} écoles (Bénin)"

            if dry_run:
                print(f"\n  [DRY-RUN] Liste: {list_name}")
                print(f"    Description: {desc}")
                for s in batch:
                    v = f" ({s.get('ville') or '?'})"
                    print(f"    #{s['num']} {s['nom']}{v}")
                    print(f"    Notes: {s['notes'][:120]}...")
                continue

            cur = conn.execute(
                "INSERT INTO lead_lists (nom, description, couleur, icone, note) VALUES (?, ?, ?, ?, ?)",
                (list_name, desc, couleur, icone, f"Catégorie {cat} \u2014 {label}")
            )
            list_id = cur.lastrowid

            for s in batch:
                lead_id = insert_lead(conn, s)
                conn.execute(
                    "INSERT OR IGNORE INTO lead_list_items (list_id, lead_id) VALUES (?, ?)",
                    (list_id, lead_id)
                )

            conn.commit()

            created.append({
                "list_id": list_id,
                "nom": list_name,
                "cat": cat,
                "count": len(batch),
                "batch": batch_num,
                "total": total_batches,
            })
            print(f"  Créée: {list_name} ({len(batch)} leads)")

    return created


def delete_existing(conn, dry_run=False):
    """Delete existing edutrack lists (Edu_*) and leads from DB."""
    rows = conn.execute(
        "SELECT id, nom FROM lead_lists WHERE nom LIKE 'Edu_%'"
    ).fetchall()

    lead_count = conn.execute(
        "SELECT COUNT(*) as c FROM leads_bruts WHERE source=?", (SOURCE,)
    ).fetchone()["c"]

    if not rows and not lead_count:
        print("  Aucune donn\u00e9e Edu_* existante.")
        return

    if dry_run:
        if rows:
            print(f"  [DRY-RUN] {len(rows)} liste(s) \u00e0 supprimer:")
            for r in rows:
                print(f"    - {r['nom']} (id={r['id']})")
        if lead_count:
            print(f"  [DRY-RUN] {lead_count} lead(s) \u00e0 supprimer (source='{SOURCE}')")
        return

    for r in rows:
        conn.execute("DELETE FROM lead_list_items WHERE list_id=?", (r["id"],))
        conn.execute("DELETE FROM lead_lists WHERE id=?", (r["id"],))
    if rows:
        print(f"  {len(rows)} liste(s) Edu_* supprim\u00e9e(s).")

    if lead_count:
        conn.execute("DELETE FROM leads_bruts WHERE source=?", (SOURCE,))
        print(f"  {lead_count} lead(s) source='{SOURCE}' supprim\u00e9(s).")
    conn.commit()


def main(batch_size=10, dry_run=False, reset=False):
    filepath = EDUTRACK_FILE
    if not os.path.exists(filepath):
        print(f"ERREUR: Fichier introuvable: {filepath}")
        sys.exit(1)

    print(f"Parsing: {filepath}")
    schools = parse_schools(filepath)
    print(f"  {len(schools)} écoles trouvées")

    by_cat = {}
    for s in schools:
        by_cat.setdefault(s["category"], []).append(s)
    print("\nRépartition par catégorie:")
    for cat in sorted(by_cat.keys()):
        print(f"  Catégorie {cat}: {len(by_cat[cat])} écoles")
    print(f"  TOTAL: {len(schools)}")

    if not schools:
        print("Aucune école trouvée. Vérifie le format du fichier.")
        return

    conn = get_conn()

    if reset:
        print("\nSuppression des listes existantes...")
        delete_existing(conn, dry_run=dry_run)

    print(f"\nCréation des listes par lots de {batch_size}...")
    created = create_lists(conn, schools, batch_size=batch_size, dry_run=dry_run)

    print(f"\n{'=' * 60}")
    print("RÉSULTAT" if not dry_run else "RÉSULTAT (DRY-RUN)")
    print(f"{'=' * 60}")
    print(f"  Listes créées : {len(created)}")
    print(f"  Total leads   : {sum(c['count'] for c in created)}")
    for c in created:
        print(f"    {c['nom']} (id={c['list_id']}) \u2014 {c['count']} leads [Cat {c['cat']}]")
    print(f"{'=' * 60}")

    conn.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Créer les listes EduTrack par catégorie A/B/C"
    )
    parser.add_argument(
        "--batch-size", type=int, default=10,
        help="Nombre de leads par liste (défaut: 10)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Afficher sans créer"
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Supprimer les listes Edu_* existantes avant de créer"
    )
    args = parser.parse_args()
    main(batch_size=args.batch_size, dry_run=args.dry_run, reset=args.reset)
