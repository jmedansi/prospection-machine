# -*- coding: utf-8 -*-
"""Génère des listes de leads par secteur, par lots de 50 leads maximum.

Le script crée des listes dans la base SQLite à partir des secteurs présents
ou d'une sélection de secteurs fournie en argument. Il exclut les leads déjà
contactés via les statuts connus de prospection.
"""

import argparse
from database.connection import get_conn

CONTACTED_STATUSES = {
    "archive", "desabonne", "contacte", "envoye", "email_sent", "repondu"
}
CONTACTED_PROSPECTION_STATUSES = CONTACTED_STATUSES.union({
    "step1_envoye", "lien_envoye", "linkedin_envoye", "formulaire_envoye", "whatsapp_envoye"
})

_DEFAULT_LIST_NAME = "Leads sans liste"
_DEFAULT_LIST_DESCRIPTION = "Leads scrapés qui ne sont encore assignés à aucune liste. Rafraîchis cette liste pour retrouver les nouveaux leads."
_DEFAULT_LIST_ICON = "📌"

_SECTOR_LABELS = {
    "immobilier": "Immobilier",
    "courtage": "Courtage",
    "concessionnaires_auto": "Concessionnaires Auto",
    "cliniques_esthetiques": "Cliniques Esthétiques",
    "ecoles_formation": "Écoles / Formation",
}

_SECTOR_ICONS = {
    "immobilier": "🏡",
    "courtage": "🏢",
    "concessionnaires_auto": "🚗",
    "cliniques_esthetiques": "💆",
    "ecoles_formation": "🎓",
}


def _human_sector_name(secteur: str) -> str:
    if not secteur:
        return "Secteur"
    return _SECTOR_LABELS.get(secteur, secteur.replace("_", " ").title())


def _chunked(iterable: list, size: int) -> list[list]:
    return [iterable[i:i + size] for i in range(0, len(iterable), size)]


def _get_uncontacted_lead_ids(conn, secteur: str) -> list[int]:
    statut_placeholders = ", ".join("?" for _ in CONTACTED_STATUSES)
    pros_statut_placeholders = ", ".join("?" for _ in CONTACTED_PROSPECTION_STATUSES)
    query = f"""
        SELECT lb.id
        FROM leads_bruts lb
        LEFT JOIN leads_audites la ON la.lead_id = lb.id
        WHERE LOWER(lb.secteur) = LOWER(?)
          AND COALESCE(LOWER(lb.statut), '') NOT IN ({statut_placeholders})
          AND COALESCE(LOWER(la.statut_prospection), '') NOT IN ({pros_statut_placeholders})
        ORDER BY lb.rating DESC, lb.nb_avis DESC, lb.date_scraping DESC
    """
    params = [secteur] + list(CONTACTED_STATUSES) + list(CONTACTED_PROSPECTION_STATUSES)
    rows = conn.execute(query, params).fetchall()
    return [r[0] for r in rows]


def _create_list_with_leads(conn, name: str, description: str, lead_ids: list[int], icon: str = "📋") -> int:
    cur = conn.execute(
        "INSERT INTO lead_lists (nom, description, icone) VALUES (?, ?, ?)",
        (name, description, icon)
    )
    list_id = cur.lastrowid
    for lead_id in lead_ids:
        try:
            conn.execute(
                "INSERT INTO lead_list_items (list_id, lead_id) VALUES (?, ?)",
                (list_id, lead_id)
            )
        except Exception:
            pass
    conn.commit()
    return list_id


def _get_unlisted_lead_ids(conn) -> list[int]:
    rows = conn.execute("""
        SELECT lb.id
        FROM leads_bruts lb
        LEFT JOIN lead_list_items lli ON lli.lead_id = lb.id
        WHERE lli.id IS NULL
        ORDER BY lb.date_scraping DESC, lb.rating DESC, lb.nb_avis DESC
    """).fetchall()
    return [r[0] for r in rows]


def _get_or_create_default_list(conn) -> int:
    row = conn.execute(
        "SELECT id FROM lead_lists WHERE nom = ?",
        (_DEFAULT_LIST_NAME,)
    ).fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO lead_lists (nom, description, icone) VALUES (?, ?, ?)",
        (_DEFAULT_LIST_NAME, _DEFAULT_LIST_DESCRIPTION, _DEFAULT_LIST_ICON)
    )
    conn.commit()
    return cur.lastrowid


def _refresh_default_list(conn) -> dict:
    default_list_id = _get_or_create_default_list(conn)
    conn.execute(
        "DELETE FROM lead_list_items WHERE list_id = ?",
        (default_list_id,)
    )
    lead_ids = _get_unlisted_lead_ids(conn)
    for lead_id in lead_ids:
        try:
            conn.execute(
                "INSERT INTO lead_list_items (list_id, lead_id) VALUES (?, ?)",
                (default_list_id, lead_id)
            )
        except Exception:
            pass
    conn.commit()
    return {"list_id": default_list_id, "count": len(lead_ids)}


def _delete_all_lists(conn) -> None:
    conn.execute("DELETE FROM lead_lists")
    conn.commit()


def run(sectors: list[str] | None = None, batch_size: int = 50, reset_existing: bool = False) -> dict:
    with get_conn() as conn:
        if reset_existing:
            _delete_all_lists(conn)

        if sectors is None:
            rows = conn.execute(
                "SELECT DISTINCT secteur FROM leads_bruts WHERE secteur IS NOT NULL AND secteur != '' ORDER BY secteur"
            ).fetchall()
            sectors = [r[0] for r in rows]

        results = {
            "created": [],
            "skipped": [],
        }

        for sector in sectors:
            lead_ids = _get_uncontacted_lead_ids(conn, sector)
            if not lead_ids:
                results["skipped"].append({"sector": sector, "reason": "aucun lead non contacté trouvé"})
                continue

            batches = _chunked(lead_ids, batch_size)
            total_batches = len(batches)
            sector_label = _human_sector_name(sector)
            icon = _SECTOR_ICONS.get(sector, "📋")

            for index, batch in enumerate(batches, start=1):
                if total_batches == 1:
                    list_name = f"{sector_label} — {len(batch)} leads non contactés"
                else:
                    list_name = f"{sector_label} — {len(batch)} leads non contactés ({index}/{total_batches})"
                description = (
                    f"Leads du secteur {sector_label}, non contactés. Batch {index}/{total_batches}."
                )
                list_id = _create_list_with_leads(conn, list_name, description, batch, icon=icon)
                results["created"].append({
                    "sector": sector,
                    "sector_label": sector_label,
                    "list_id": list_id,
                    "nom": list_name,
                    "count": len(batch),
                    "batch": index,
                    "total_batches": total_batches,
                })

        return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Génère des listes de leads par secteur en lots de 50.")
    parser.add_argument("--sectors", nargs="*", help="Liste de secteurs à traiter (ex: immobilier cliniques_esthetiques)")
    parser.add_argument("--batch-size", type=int, default=50, help="Taille maximale de chaque liste de leads")
    parser.add_argument("--reset-existing", action="store_true", help="Supprime toutes les listes existantes avant de créer les nouvelles")
    parser.add_argument("--refresh-default", action="store_true", help="Crée ou met à jour la liste par défaut des leads non assignés")
    args = parser.parse_args()

    if args.batch_size < 1 or args.batch_size > 1000:
        raise SystemExit("batch-size doit être entre 1 et 1000")

    with get_conn() as conn:
        if args.reset_existing:
            conn.execute("DELETE FROM lead_lists")
            conn.commit()
            print("Toutes les listes existantes ont été supprimées.")

        if args.refresh_default:
            default_id = _get_or_create_default_list(conn)
            conn.execute("DELETE FROM lead_list_items WHERE list_id = ?", (default_id,))
            unlisted = _get_unlisted_lead_ids(conn)
            for lead_id in unlisted:
                try:
                    conn.execute("INSERT INTO lead_list_items (list_id, lead_id) VALUES (?, ?)", (default_id, lead_id))
                except Exception:
                    pass
            conn.commit()
            print(f"Liste par défaut mise à jour : id={default_id}, leads={len(unlisted)}")

    result = run(sectors=args.sectors or None, batch_size=args.batch_size, reset_existing=False)
    print("Listes créées :")
    for item in result["created"]:
        print(f" - [{item['sector']}] {item['nom']} (id={item['list_id']}, count={item['count']})")

    if result["skipped"]:
        print("\nSecteurs ignorés :")
        for item in result["skipped"]:
            print(f" - {item['sector']}: {item['reason']}")


if __name__ == "__main__":
    main()
