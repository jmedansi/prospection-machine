"""Mentions légales — enrichit les leads source='ads' des 5 secteurs prioritaires"""
import logging, sys, os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

from database.connection import get_conn
from enrichisseur.mentions_legales_enricher import enrichir_lead, _format_notes, update_db

SECTEURS_PRIORITAIRES = [
    "immobilier",
    "courtage",
    "concessionnaires_auto",
    "cliniques_esthetiques",
    "ecoles_formation",
]

def get_ads_leads(secteurs: list[str]) -> list[dict]:
    """Retourne les leads source='ads' des secteurs donnés avec notes vides."""
    placeholders = ",".join("?" for _ in secteurs)
    with get_conn() as conn:
        sql = f"""
            SELECT id, nom, site_web
            FROM leads_bruts
            WHERE source = 'ads'
              AND secteur IN ({placeholders})
              AND site_web IS NOT NULL AND site_web != ''
              AND (notes IS NULL OR notes = '')
            ORDER BY id
        """
        rows = conn.execute(sql, secteurs).fetchall()
        return [dict(r) for r in rows]

def main():
    leads = get_ads_leads(SECTEURS_PRIORITAIRES)
    total = len(leads)
    if total == 0:
        print("✅ Aucun lead ADS à enrichir (notes déjà remplies ou pas de site web).")
        return

    print(f"[...] {total} leads ADS a traiter (secteurs: {', '.join(SECTEURS_PRIORITAIRES)})\n")
    ok = 0
    skip = 0

    for i, lead in enumerate(leads, 1):
        lid = lead["id"]
        nom = lead["nom"] or "(sans nom)"
        url = lead["site_web"]

        print(f"[{i:3d}/{total}] #{lid:5d} {nom[:40]:40s}", end="  ", flush=True)

        result = enrichir_lead(lid, url, nom)
        notes = _format_notes(result)

        if not notes:
            print("⏭️  rien trouvé")
            skip += 1
            # Sauvegarde quand même notes='mentions_introuvables' pour éviter re-scrape
            update_db(lid, "mentions_introuvables", result)
            continue

        update_db(lid, notes, result)
        dirigeant = f"{result['dirigeant_prenom'] or ''} {result['dirigeant_nom'] or ''}".strip()
        emails = ", ".join(result["emails"][:2]) if result["emails"] else ""
        print(f"✓ {dirigeant[:25]:25s} | {emails[:30]:30s}")
        ok += 1

    print(f"\nRésumé: {ok} enrichis, {skip} sans mentions, {total} total")

if __name__ == "__main__":
    main()
