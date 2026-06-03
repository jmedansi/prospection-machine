import sys, os, logging
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path: sys.path.insert(0, ROOT)
logging.basicConfig(level=logging.INFO, format="%(message)s")

from database.connection import get_conn
from core.contact_finder import find_contacts

# Leads qui n'ont pas encore d'email
ids = [3674, 3675, 3676, 3677]  # Elysees Derm, Clinique La Marina, Boclinic, Docteur Filler

with get_conn() as conn:
    for lid in ids:
        row = conn.execute("SELECT id, nom, site_web FROM leads_bruts WHERE id=?", (lid,)).fetchone()
        if not row: continue
        lid, nom, site = row
        if not site: continue
        print(f"\n#{lid} {nom}")
        print(f"   site: {site}")
        try:
            contacts = find_contacts(site, nom, enrich_ceo=True, fast_mode=False)
            updates = {}
            if contacts.get("email_valide"):
                updates["email"] = contacts.get("email_contact", "")
                updates["email_valide"] = contacts["email_valide"]
            elif contacts.get("email_contact"):
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
            print(f"   email: {contacts.get('email_valide') or contacts.get('email_contact') or '--'}")
            print(f"   CEO:   {contacts.get('ceo_prenom', '') or ''} {contacts.get('ceo_nom', '') or ''}")
        except Exception as e:
            print(f"   ERREUR: {e}")
            import traceback; traceback.print_exc()

print("\nTerminé.")
