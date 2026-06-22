# -*- coding: utf-8 -*-
"""
scripts/create_benin_lists.py — Créer des listes de 10 leads Bénin par secteur

Regroupe les leads Bénin sans site web par secteur (basé sur mot_cle),
puis crée des listes de 10 leads dans lead_lists.

Usage:
    python scripts/create_benin_lists.py
    python scripts/create_benin_lists.py --batch-size 5
    python scripts/create_benin_lists.py --dry-run
"""

import sys
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from database.connection import get_conn

# ─── Mapping mot_cle -> secteur label ──────────────────────────────────────

MOT_CLE_TO_SECTEUR = {
    "hotel": "Hotellerie",
    "hôtel": "Hotellerie",
    "restaurant": "Restauration",
    "cabinet medical": "Sante",
    "cabinet médical": "Sante",
    "pharmacie": "Sante",
    "cabinet notaire": "Notaire",
    "cabinet comptable": "Comptabilite",
    "agence immobilière": "Immobilier",
    "agence immobiliere": "Immobilier",
    "auto-école": "Auto-ecole",
    "auto_ecole": "Auto-ecole",
    "salon coiffure": "Esthetique",
    "salon de coiffure": "Esthetique",
    "barbier": "Esthetique",
    "avocat": "Avocat",
    "kinésithérapeute": "Kinesitherapie",
    "kinesitherapeute": "Kinesitherapie",
    "cabinet de kiné": "Kinesitherapie",
    "cabinet de kine": "Kinesitherapie",
    "physiothérapie": "Kinesitherapie",
    "massage": "Kinesitherapie",
}

SECTEUR_LABELS = {
    "Hotellerie": "Hotels",
    "Restauration": "Restauration",
    "Sante": "Sante",
    "Notaire": "Notaires",
    "Comptabilite": "Comptabilite",
    "Immobilier": "Immobilier",
    "Auto-ecole": "Auto-ecoles",
    "Esthetique": "Esthetique",
    "Avocat": "Avocats",
    "Kinesitherapie": "Kinesitherapie",
    "Divers": "Divers",
}


def _classify(mot_cle, nom):
    """Classifie un lead en secteur basé sur mot_cle et nom."""
    if not mot_cle:
        mot_cle = ""
    mc = mot_cle.lower().strip()

    for key, secteur in MOT_CLE_TO_SECTEUR.items():
        if key in mc:
            return secteur

    # Fallback basé sur le nom
    nom_lower = (nom or "").lower()
    if any(w in nom_lower for w in ["hotel", "hôtel", "guesthouse", "guest house", "residence", "appart"]):
        return "Hotellerie"
    if any(w in nom_lower for w in ["restaurant", "resto", "bar", "cafe", "brasserie", "grillade"]):
        return "Restauration"
    if any(w in nom_lower for w in ["cabinet", "medical", "clinique", "pharmacie", "sante"]):
        return "Sante"
    if any(w in nom_lower for w in ["avocat", "cabinet d'avocats"]):
        return "Avocat"
    if any(w in nom_lower for w in ["kiné", "kine", "massage", "physio"]):
        return "Kinesitherapie"

    return "Divers"


def main(batch_size=10, dry_run=False):
    """Crée les listes Bénin par secteur."""
    conn = get_conn()

    # 1. Charger les leads Bénin sans site
    rows = conn.execute("""
        SELECT id, nom, mot_cle, secteur, rating, nb_avis, ville
        FROM leads_bruts
        WHERE pays = 'bj'
          AND (site_web IS NULL OR site_web = '')
          AND statut NOT IN ('archive', 'bounced', 'desabonne')
        ORDER BY mot_cle, rating DESC, nb_avis DESC
    """).fetchall()

    if not rows:
        print("Aucun lead Bénin sans site trouve.")
        return

    # 2. Classifier par secteur
    secteurs = {}
    for r in rows:
        lead = dict(r)
        secteur = _classify(lead.get("mot_cle"), lead.get("nom"))
        if secteur not in secteurs:
            secteurs[secteur] = []
        secteurs[secteur].append(lead)

    # 3. Afficher les statistiques
    print("\n=== Leads Benin sans site par secteur ===")
    for sect_name, leads in sorted(secteurs.items(), key=lambda x: -len(x[1])):
        label = SECTEUR_LABELS.get(sect_name, sect_name)
        print(f"  {label:25s} {len(leads):4d} leads")
    print(f"  {'TOTAL':25s} {sum(len(v) for v in secteurs.values()):4d}")

    # 4. Supprimer les anciennes listes Benin si existantes
    if not dry_run:
        existing = conn.execute(
            "SELECT id, nom FROM lead_lists WHERE nom LIKE '%Benin%' OR nom LIKE '%Benin%'"
        ).fetchall()
        if existing:
            print(f"\nSuppression de {len(existing)} anciennes listes Benin...")
            for r in existing:
                conn.execute("DELETE FROM lead_list_items WHERE list_id=?", (r["id"],))
                conn.execute("DELETE FROM lead_lists WHERE id=?", (r["id"],))
            conn.commit()

    # 5. Creer les listes
    created = []
    for sect_name, leads in sorted(secteurs.items(), key=lambda x: -len(x[1])):
        label = SECTEUR_LABELS.get(sect_name, sect_name)

        # Découper en batch de batch_size
        for batch_idx in range(0, len(leads), batch_size):
            batch = leads[batch_idx:batch_idx + batch_size]
            total_batches = (len(leads) + batch_size - 1) // batch_size

            if total_batches > 1:
                list_name = f"BJ {label} — {len(batch)} leads sans site ({batch_idx//batch_size + 1}/{total_batches})"
            else:
                list_name = f"BJ {label} — {len(batch)} leads sans site"

            if dry_run:
                print(f"\n  [DRY-RUN] Liste: {list_name}")
                for lead in batch:
                    print(f"    #{lead['id']} {lead['nom'][:40]} (note={lead.get('rating') or '-'})")
                continue

            # Creer la liste
            cur = conn.execute(
                "INSERT INTO lead_lists (nom, description, couleur, icone) VALUES (?, ?, ?, ?)",
                (list_name, f"Leads Bénin sans site - {label}", "#6366f1", "🇧🇯")
            )
            list_id = cur.lastrowid

            # Ajouter les leads
            for lead in batch:
                conn.execute(
                    "INSERT OR IGNORE INTO lead_list_items (list_id, lead_id) VALUES (?, ?)",
                    (list_id, lead["id"])
                )

            conn.commit()

            created.append({
                "sector": sect_name,
                "sector_label": label,
                "list_id": list_id,
                "nom": list_name,
                "count": len(batch),
                "batch": batch_idx // batch_size + 1,
                "total_batches": total_batches,
            })
            print(f"  Cree: {list_name} ({len(batch)} leads)")

    # 6. Résumé
    print(f"\n{'='*60}")
    print(f"RECAPITULATIF")
    print(f"{'='*60}")
    print(f"  Listes creees : {len(created)}")
    print(f"  Total leads   : {sum(c['count'] for c in created)}")
    for c in created:
        print(f"    {c['nom']} (id={c['list_id']})")
    print(f"{'='*60}")

    conn.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Creer les listes Bénin par secteur")
    parser.add_argument("--batch-size", type=int, default=10, help="Nombre de leads par liste")
    parser.add_argument("--dry-run", action="store_true", help="Afficher sans creer")
    args = parser.parse_args()
    main(batch_size=args.batch_size, dry_run=args.dry_run)
