"""
Insère 10 leads chirurgie esthétique (Google Ads) dans leads_bruts,
puis les enrichit (email, CEO) sans audit.
Source='ads' → automatiquement exclu de l'audit.
"""
import sys, os, logging
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

LEADS = [
    {"nom": "Dr Vincent Nguyen - Chirurgie Esthétique Paris", "site_web": "https://www.chirurgie-esthetique.paris", "telephone": "+33142744683", "ville": "Paris", "mot_cle": "chirurgie esthétique Paris"},
    {"nom": "Dr Muriel Perrault de Jotemps", "site_web": "https://drmurielperraultdejotemps.com", "telephone": "", "ville": "Paris", "mot_cle": "chirurgien esthétique Paris"},
    {"nom": "Clinique des Champs-Élysées", "site_web": "https://cliniquedeschampselysees.com", "telephone": "", "ville": "Paris", "mot_cle": "chirurgien esthétique Paris"},
    {"nom": "Dermocare Beauty Repair", "site_web": "https://dermocarebeautyrepair.fr", "telephone": "", "ville": "Paris", "mot_cle": "chirurgien esthétique Paris"},
    {"nom": "Elysees Derm", "site_web": "https://elysees-derm.com", "telephone": "", "ville": "Paris", "mot_cle": "chirurgien esthétique Paris"},
    {"nom": "Nescens Paris", "site_web": "https://nescens.com", "telephone": "", "ville": "Paris", "mot_cle": "clinique esthétique Paris"},
    {"nom": "The Clinic", "site_web": "https://the-clinic.fr", "telephone": "", "ville": "Paris", "mot_cle": "médecine esthétique Paris"},
    {"nom": "Clinique La Marina", "site_web": "https://cliniquelamarina.com", "telephone": "", "ville": "Paris", "mot_cle": "médecine esthétique Paris"},
    {"nom": "Boclinic", "site_web": "https://boclinic.fr", "telephone": "", "ville": "Paris", "mot_cle": "médecine esthétique Paris"},
    {"nom": "Docteur Filler", "site_web": "https://docteurfiller.com", "telephone": "", "ville": "Paris", "mot_cle": "clinique esthétique Paris"},
]

def main():
    from database.leads import insert_lead
    from core.contact_finder import find_contacts

    inserted = []
    for lead in LEADS:
        lid = insert_lead({
            "nom": lead["nom"],
            "site_web": lead["site_web"],
            "telephone": lead["telephone"],
            "ville": lead["ville"],
            "mot_cle": lead["mot_cle"],
            "source": "ads",
            "rating": 0,
        })
        if lid:
            inserted.append((lid, lead))
            logger.info(f"  #{lid} {lead['nom']:45s} {lead['site_web']}")
        else:
            logger.warning(f"  Duplicata: {lead['nom']}")

    logger.info(f"\n{len(inserted)} leads insérés. Enrichissement en cours...\n")

    for lid, lead in inserted:
        logger.info(f"→ #{lid} {lead['nom']}")
        try:
            contacts = find_contacts(lead["site_web"], lead["nom"], enrich_ceo=True, fast_mode=False)

            from database.connection import get_conn
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
            import traceback; traceback.print_exc()

    logger.info(f"\nTerminé. {len(inserted)} leads insérés et enrichis.")

if __name__ == "__main__":
    main()
