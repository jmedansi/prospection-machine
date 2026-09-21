"""Inject courtage leads ADS + enrichir"""
import sys, os, logging
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

LEADS = [
    {"nom": "Cyberpret", "site_web": "https://cyberpret.com", "ville": "", "mot_cle": "courtier prêt immobilier Bordeaux"},
    {"nom": "Simulations Cyberpret", "site_web": "https://simulations.cyberpret.com", "ville": "", "mot_cle": "courtier prêt immobilier Bordeaux"},
    {"nom": "Helix Assurance", "site_web": "https://helixassurance.fr", "ville": "", "mot_cle": "courtier prêt immobilier Nice"},
    {"nom": "La Centrale de Financement", "site_web": "https://lacentraledefinancement.fr", "ville": "", "mot_cle": "courtier prêt immobilier Nice"},
    {"nom": "Empruntis", "site_web": "https://empruntis.com", "ville": "", "mot_cle": "courtier prêt immobilier Nice"},
    {"nom": "SARL Finanx", "site_web": "https://sarlfinanx.com", "ville": "", "mot_cle": "courtier prêt immobilier Nice"},
    {"nom": "Pretto", "site_web": "https://pretto.fr", "ville": "", "mot_cle": "comparateur courtier immobilier Paris"},
    {"nom": "Courtier Pretto", "site_web": "https://courtier.pretto.fr", "ville": "", "mot_cle": "comparateur courtier immobilier Paris"},
    {"nom": "App Pretto", "site_web": "https://app.pretto.fr", "ville": "", "mot_cle": "comparateur courtier immobilier Paris"},
    {"nom": "Immo G2C", "site_web": "https://immog2c.fr", "ville": "", "mot_cle": "comparateur courtier immobilier Paris"},
    {"nom": "Pret Immobilier ImmoG2C", "site_web": "https://pret-immobilier.immog2c.fr", "ville": "", "mot_cle": "comparateur courtier immobilier Paris"},
    {"nom": "Sully Immobilier", "site_web": "https://sully-immobilier.fr", "ville": "", "mot_cle": "comparateur courtier immobilier Paris"},
    {"nom": "Realadvisor", "site_web": "https://realadvisor.fr", "ville": "", "mot_cle": "comparateur courtier immobilier Paris"},
    {"nom": "Accueil Immo", "site_web": "https://accueil.immo", "ville": "", "mot_cle": "comparateur courtier immobilier Paris"},
]

def main():
    from database.leads import insert_lead
    from core.contact_finder import find_contacts
    from database.connection import get_conn

    inserted = []
    for lead in LEADS:
        lid = insert_lead({
            "nom": lead["nom"],
            "site_web": lead["site_web"],
            "telephone": "",
            "ville": lead["ville"],
            "mot_cle": lead["mot_cle"],
            "source": "ads",
            "secteur": "courtage",
            "rating": 0,
        })
        if lid:
            inserted.append((lid, lead))
            logger.info(f"  #{lid} {lead['nom']:45s} {lead['site_web']}")
        else:
            logger.warning(f"  Duplicata: {lead['nom']}")

    logger.info(f"\n{len(inserted)} leads courtage insérés. Enrichissement...\n")

    for lid, lead in inserted:
        logger.info(f"→ #{lid} {lead['nom']}")
        try:
            contacts = find_contacts(lead["site_web"], lead["nom"], pays=lead.get("pays", "fr"), enrich_ceo=True, fast_mode=False)
            with get_conn() as conn:
                updates = {}
                if contacts.get("email_valide"):
                    updates["email_valide"] = contacts["email_valide"]
                    updates["email"] = contacts.get("email_contact", "")
                if contacts.get("email_contact"):
                    updates["email"] = contacts["email_contact"]
                if contacts.get("telephone"):
                    updates["telephone"] = contacts["telephone"]
                if contacts.get("ceo_prenom_norm"):
                    updates["prenom_gerant"] = contacts["ceo_prenom_norm"]
                if contacts.get("ceo_nom_norm"):
                    updates["nom_gerant"] = contacts["ceo_nom_norm"]
                if updates:
                    set_clause = ", ".join(f"{k}=?" for k in updates)
                    conn.execute(f"UPDATE leads_bruts SET {set_clause} WHERE id=?", list(updates.values()) + [lid])
                    conn.commit()

            email = contacts.get("email_valide") or contacts.get("email_contact") or "—"
            ceo = f"{contacts.get('ceo_prenom', '') or ''} {contacts.get('ceo_nom', '') or ''}".strip() or "—"
            logger.info(f"  email: {email}")
            logger.info(f"  CEO:   {ceo}")
        except Exception as e:
            logger.error(f"  Erreur: {e}")

    logger.info(f"\nTerminé. {len(inserted)} leads courtage insérés et enrichis.")

if __name__ == "__main__":
    main()
