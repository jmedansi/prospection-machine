# -*- coding: utf-8 -*-
"""
scraper_no_site_batch.py
Lance des scrapings Google Maps pour collecter 50 leads SANS site web
en France et 50 au Bénin, puis les organise dans deux listes dédiées.
Utilise CityRotator pour une rotation intelligente des villes par pays.
"""
import sys
import os
import asyncio
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.connection import get_conn
from scraper.main import main_async
from services.campaign_tracker import create_campaign, complete_campaign
from core.city_rotator import CityRotator

# Configuration
KEYWORDS = ["hôtel", "agence immobilière", "cabinet médical", "cabinet notaire", "cabinet comptable"]

LIMIT_PER_CAMPAIGN = 100  # Scraper 100 pour en obtenir ~50 sans site
TARGET_NO_SITE = 50


def get_leads_without_site(ville: str, limit: int = 25) -> list:
    """Retourne les IDs des leads sans site web pour une ville."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT id FROM leads_bruts
            WHERE ville = ?
              AND (site_web IS NULL OR site_web = '' OR TRIM(site_web) = '')
              AND statut = 'en_attente'
            ORDER BY date_scraping DESC
            LIMIT ?
        """, (ville, limit)).fetchall()
    return [r[0] for r in rows]


def create_list_and_add_leads(name: str, description: str, lead_ids: list, icon: str = "📋") -> int:
    """Crée une liste et ajoute les leads dedans."""
    if not lead_ids:
        print(f"  ⚠️  Aucun lead à ajouter à '{name}'")
        return None
    
    with get_conn() as conn:
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
        print(f"  ✅ Liste créée: '{name}' (ID: {list_id}, {len(lead_ids)} leads)")
        return list_id


async def scrape_batch(keywords: list, pays: str, country_code: str):
    """Lance une série de scrapings avec rotation de villes via CityRotator."""
    print(f"\n{'='*70}")
    print(f"SCRAPING {pays.upper()} — Chercher {TARGET_NO_SITE} leads SANS site web")
    print(f"{'='*70}")

    rotator = CityRotator(country=country_code, keywords=keywords, source="no_site")
    all_no_site_leads = set()

    for keyword in keywords:
        if len(all_no_site_leads) >= TARGET_NO_SITE:
            break

        while len(all_no_site_leads) < TARGET_NO_SITE and rotator.has_more():
            batch = rotator.next_batch(keyword, batch_size=1)
            if not batch:
                break

            city = batch[0].rsplit(" ", 1)[-1]

            current_no_site = len(all_no_site_leads)
            print(f"\nScraping: '{keyword}' @ {city}")
            print(f"   Leads sans site actuels: {current_no_site}/{TARGET_NO_SITE}")

            campaign_name = f"NoSite-{pays}-{keyword}-{city}"
            camp_id = create_campaign(
                campaign_name,
                secteur=f"no_site_{pays}",
                ville=city,
                source='maps',
                nb_demande=LIMIT_PER_CAMPAIGN,
                pays=country_code,
            )

            try:
                await main_async([
                    '--keyword', keyword,
                    '--city', city,
                    '--country', country_code,
                    '--site-filter', 'without_site',
                    '--limit', str(LIMIT_PER_CAMPAIGN),
                    '--campaign-id', str(camp_id),
                ])
                complete_campaign(camp_id)
            except Exception as e:
                print(f"   Erreur: {e}")
                continue

            new_leads = get_leads_without_site(city, TARGET_NO_SITE - current_no_site)
            all_no_site_leads.update(new_leads)
            print(f"   -> {len(new_leads)} leads sans site trouves (total: {len(all_no_site_leads)})")

            rotator.mark_used(batch)
            await asyncio.sleep(2)

    return list(all_no_site_leads)[:TARGET_NO_SITE]


async def main():
    print("\n" + "="*70)
    print("🎯 COLLECTE LEADS SANS SITE WEB — France & Bénin")
    print(f"   Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    # Phase 1: Scraper en France
    print("\n" + "─"*70)
    print("PHASE 1  FRANCE")
    print("─"*70)
    france_leads = await scrape_batch(KEYWORDS, "france", "fr")
    
    # Phase 2: Scraper au Bénin
    print("\n" + "─"*70)
    print("PHASE 2  BENIN")
    print("─"*70)
    benin_leads = await scrape_batch(KEYWORDS, "benin", "bj")
    
    # Phase 3: Créer les listes
    print("\n" + "─"*70)
    print("PHASE 3️⃣  CRÉATION DES LISTES")
    print("─"*70)
    
    france_list_id = create_list_and_add_leads(
        name="Leads SANS site - France (25)",
        description=f"25 leads francais sans site web, scrapes le {datetime.now().strftime('%Y-%m-%d %H:%M')}. A traiter en priorite pour proposition de creation de site.",
        lead_ids=france_leads,
        icon="FR"
    )
    
    benin_list_id = create_list_and_add_leads(
        name="Leads SANS site - Benin (25)",
        description=f"25 leads beninois sans site web, scrapes le {datetime.now().strftime('%Y-%m-%d %H:%M')}. A traiter en priorite pour proposition de creation de site.",
        lead_ids=benin_leads,
        icon="BJ"
    )
    
    # Résumé final
    print("\n" + "="*70)
    print("✅ MISSION TERMINÉE")
    print("="*70)
    print(f"France:  {len(france_leads)} leads → Liste #{france_list_id}")
    print(f"Bénin:   {len(benin_leads)} leads → Liste #{benin_list_id}")
    print("="*70)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️  Interruption utilisateur")
    except Exception as e:
        print(f"\n❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
