"""Extraction Google Ads + injection DB pour les 5 secteurs prioritaires"""
import asyncio, logging, sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

from scraper.sniper.headless_extract import search_one, clean
from database.leads import insert_lead
from core.contact_finder import find_contacts
from database.connection import get_conn

SECTORS = {
    "immobilier": [
        "agence immobilière Paris",
        "estimation immobilière Paris",
        "agent immobilier Paris",
        "agence immobilière Lyon",
    ],
    "courtage": [
        "courtier prêt immobilier Paris",
        "simulation crédit immobilier Paris",
        "courtier immobilier Paris",
        "courtier prêt immobilier Lyon",
    ],
    "garages": [
        "garage Paris",
        "garage automobile Paris",
        "garage Lyon",
        "garage automobile Lyon",
    ],
    "cliniques_esthetiques": [
        "chirurgie esthétique Paris",
        "médecine esthétique Paris",
        "clinique esthétique Paris",
        "chirurgie esthétique Lyon",
    ],
    "ecoles_formation": [
        "formation comptabilité Paris",
        "reconversion professionnelle Paris",
        "centre de formation Paris",
        "formation professionnelle Lyon",
    ],
}

PORT_BASE = 9500

async def run_sector(secteur: str, keywords: list[str]) -> list[dict]:
    """Extract ads domains for a sector and return lead dicts."""
    seen_domains = set()
    leads = []
    for i, kw in enumerate(keywords):
        port = PORT_BASE + i
        logger.info(f"  [{secteur}] recherche: '{kw}' (port {port})")
        domains = await search_one(kw, port)
        if not domains:
            logger.info(f"    -> 0 annonces")
            continue
        for url in domains:
            domain_clean = clean(url)
            if domain_clean and domain_clean not in seen_domains:
                seen_domains.add(domain_clean)
                nom = domain_clean.replace("https://", "").replace("http://", "").rstrip("/")
                leads.append({
                    "nom": nom,
                    "site_web": domain_clean,
                    "telephone": "",
                    "ville": "",
                    "mot_cle": kw,
                    "source": "ads",
                    "secteur": secteur,
                    "rating": 0,
                })
                logger.info(f"    ✓ {domain_clean}")
        await asyncio.sleep(2)
    return leads

def inject_and_enrich(leads: list[dict]):
    """Insert leads into DB and enrich with contacts."""
    inserted = []
    for lead in leads:
        lid = insert_lead(lead)
        if lid:
            inserted.append((lid, lead))
            logger.info(f"  #{lid} {lead['nom'][:45]:45s} {lead['site_web']}")
        else:
            logger.info(f"  Duplicata: {lead['nom']}")

    logger.info(f"\n→ {len(inserted)} leads insérés. Enrichissement contacts...\n")

    for lid, lead in inserted:
        logger.info(f"→ #{lid} {lead['nom']}")
        try:
            contacts = find_contacts(lead["site_web"], lead["nom"], enrich_ceo=True, fast_mode=False)
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

    return inserted

async def main():
    total_leads = 0
    for secteur, keywords in SECTORS.items():
        print(f"\n{'='*60}")
        print(f"Secteur: {secteur} ({len(keywords)} keywords)")
        print(f"{'='*60}")
        leads = await run_sector(secteur, keywords)
        if not leads:
            print(f"  Aucun lead trouvé pour {secteur}")
            continue
        injected = inject_and_enrich(leads)
        total_leads += len(injected)
        print(f"  → {len(injected)} leads {secteur}")

    print(f"\n{'='*60}")
    print(f"Terminé: {total_leads} leads ADS injectés au total")

if __name__ == "__main__":
    asyncio.run(main())
