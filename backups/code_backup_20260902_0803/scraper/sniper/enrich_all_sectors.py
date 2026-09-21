"""Enrichit tous les leads ADS sans email — par secteur, avec progression"""
import sys, os, logging, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from database.connection import get_conn
from core.contact_finder import find_contacts

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

def main():
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT id, nom, site_web, secteur, pays FROM leads_bruts "
            "WHERE source='ads' AND secteur IS NOT NULL AND secteur != '' "
            "AND (email_valide IS NULL OR email_valide = '') "
            "ORDER BY secteur, id"
        )
        leads = cur.fetchall()

    logger.info(f"{len(leads)} leads à enrichir\n")

    ok = 0
    for i, (lid, nom, site_web, secteur, pays) in enumerate(leads, 1):
        if not site_web:
            logger.info(f"[{i}/{len(leads)}] #{lid} {nom[:40]:40s} — pas de site web, skip")
            continue

        logger.info(f"[{i}/{len(leads)}] [{secteur:25s}] #{lid} {nom[:40]:40s} {site_web}")
        try:
            contacts = find_contacts(site_web, nom, pays=pays or "fr", enrich_ceo=True, fast_mode=False)

            updates = {}
            if contacts.get("email_valide"):
                updates["email_valide"] = contacts["email_valide"]
                updates["email"] = contacts.get("email_contact", "")
            if contacts.get("email_contact") and "email" not in updates:
                updates["email"] = contacts["email_contact"]
            if contacts.get("telephone"):
                updates["telephone"] = contacts["telephone"]
            if contacts.get("ceo_prenom_norm"):
                updates["prenom_gerant"] = contacts["ceo_prenom_norm"]
            if contacts.get("ceo_nom_norm"):
                updates["nom_gerant"] = contacts["ceo_nom_norm"]

            if updates:
                with get_conn() as conn2:
                    set_clause = ", ".join(f"{k}=?" for k in updates)
                    conn2.execute(f"UPDATE leads_bruts SET {set_clause} WHERE id=?", list(updates.values()) + [lid])
                    conn2.commit()

            email = contacts.get("email_valide") or contacts.get("email_contact") or "—"
            ceo = f"{contacts.get('ceo_prenom', '') or ''} {contacts.get('ceo_nom', '') or ''}".strip() or "—"
            logger.info(f"  ✓ email={email} CEO={ceo}")
            if email != "—":
                ok += 1
        except Exception as e:
            logger.error(f"  ✗ Erreur: {e}")

    logger.info(f"\nTerminé. {ok}/{len(leads)} leads enrichis avec email.")

if __name__ == "__main__":
    main()
