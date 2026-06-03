# -*- coding: utf-8 -*-
"""
run_sector_campaigns.py — Orchestrateur multi-secteurs autonome.

Lance les campagnes Maps + Ads pour 5 secteurs, surveille la progression,
et relance avec des villes supplémentaires jusqu'à atteindre les quotas.

Usage :
    python run_sector_campaigns.py [--dry-run]
"""

import os
import sys
import json
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(ROOT, 'data', 'logs', 'sector_campaigns.log'), encoding='utf-8'),
    ]
)
logger = logging.getLogger('sector_campaigns')

# ─── Configuration des secteurs ────────────────────────────────────────────────

SECTORS = [
    {
        "name": "immobilier",
        "maps_keywords": ["agence immobilière", "agent immobilier"],
        "ads_keywords": [
            "agence immobilière", "agent immobilier", "acheter appartement",
            "vendre maison", "estimation immobilière",
        ],
    },
    {
        "name": "courtage",
        "maps_keywords": ["courtier", "cabinet de courtage", "courtier en assurance"],
        "ads_keywords": [
            "courtier en assurance", "courtier en crédit", "courtier en prêt",
            "assurance habitation", "crédit immobilier",
        ],
    },
    {
        "name": "concessionnaires_auto",
        "maps_keywords": ["concessionnaire automobile", "concession auto", "garage automobile"],
        "ads_keywords": [
            "concessionnaire auto", "voiture neuve", "acheter voiture",
            "concession automobile", "véhicule neuf",
        ],
    },
    {
        "name": "cliniques_esthetiques",
        "maps_keywords": ["clinique esthétique", "médecine esthétique", "centre esthétique"],
        "ads_keywords": [
            "médecine esthétique", "injection botox", "chirurgie esthétique",
            "laser esthétique", "centre esthétique",
        ],
    },
    {
        "name": "ecoles_formation",
        "maps_keywords": ["centre de formation", "organisme de formation", "école de formation"],
        "ads_keywords": [
            "formation professionnelle", "centre de formation",
            "formation continue", "formation qualifiante",
        ],
    },
]

BIG_CITIES = [
    "Paris", "Lyon", "Marseille", "Bordeaux", "Toulouse",
    "Lille", "Nice", "Nantes", "Strasbourg", "Montpellier",
]

MEDIUM_CITIES = [
    "Rennes", "Rouen", "Toulon", "Grenoble", "Dijon",
    "Angers", "Nîmes", "Aix-en-Provence", "Saint-Étienne", "Tours",
    "Reims", "Clermont-Ferrand", "Orléans", "Le Havre", "Brest",
    "Metz", "Perpignan", "Besançon", "Limoges", "Caen",
]

QUOTA_MAPS = 20
QUOTA_ADS = 15
MIN_REVIEWS = 50


# ─── Base de données ───────────────────────────────────────────────────────────

def count_leads_by_sector(sector: str, source: str = None) -> int:
    from database import get_conn
    with get_conn() as conn:
        if source:
            row = conn.execute(
                "SELECT COUNT(*) FROM leads_bruts WHERE secteur=? AND source=?",
                (sector, source)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) FROM leads_bruts WHERE secteur=?",
                (sector,)
            ).fetchone()
    return row[0] if row else 0


def count_maps_leads_50plus(sector: str) -> int:
    from database import get_conn
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM leads_bruts WHERE secteur=? AND source='maps' AND nb_avis >= ?",
            (sector, MIN_REVIEWS)
        ).fetchone()
    return row[0] if row else 0


def wait_for_campaigns_to_complete(campaign_ids: set, timeout_hours: int = 4, poll_seconds: int = 30):
    """Attend que les campagnes spécifiées soient terminées (phase='done','failed','stopped')."""
    if not campaign_ids:
        return True
    deadline = time.time() + timeout_hours * 3600
    ids_str = ",".join(str(i) for i in campaign_ids)
    while time.time() < deadline:
        from database import get_conn
        with get_conn() as conn:
            active = conn.execute(
                f"SELECT COUNT(*) FROM campagnes WHERE id IN ({ids_str}) AND phase IN ('pending', 'scraping', 'enrichment')"
            ).fetchone()[0]
        if active == 0:
            logger.info("  ✓ Toutes les campagnes sont terminées.")
            return True
        logger.info(f"  ⏳ {active}/{len(campaign_ids)} campagne(s) en cours... (poll {poll_seconds}s)")
        time.sleep(poll_seconds)
    logger.warning(f"  ⚠️ Timeout après {timeout_hours}h — campagnes encore actives: {campaign_ids}")
    return False


# ─── Lancement Maps ────────────────────────────────────────────────────────────

def launch_maps_for_sector(sector_cfg: Dict):
    """Lance les campagnes Maps pour un secteur, ville par ville."""
    from services.scraper_runner import launch_scraper

    sector = sector_cfg["name"]
    keywords = sector_cfg["maps_keywords"]
    all_cities = BIG_CITIES + MEDIUM_CITIES
    pending_ids = set()

    logger.info(f"\n{'='*70}")
    logger.info(f"🗺️  MAPS — Secteur : {sector}")
    logger.info(f"    Quota : {QUOTA_MAPS} leads (min {MIN_REVIEWS} avis)")
    logger.info(f"{'='*70}")

    for keyword in keywords:
        current = count_maps_leads_50plus(sector)
        if current >= QUOTA_MAPS:
            logger.info(f"  ✓ Quota déjà atteint pour '{keyword}' ({current}/{QUOTA_MAPS})")
            continue

        remaining = QUOTA_MAPS - current
        logger.info(f"  Keyword : '{keyword}' — besoin de {remaining} leads supplémentaires")

        for city in all_cities:
            current = count_maps_leads_50plus(sector)
            if current >= QUOTA_MAPS:
                logger.info(f"  ✓ Quota atteint ! ({current}/{QUOTA_MAPS})")
                break

            already_launched = _campaign_exists(sector, keyword, city)
            if already_launched:
                logger.info(f"  — Campagne déjà lancée pour {keyword} @ {city}, skip")
                continue

            remaining = QUOTA_MAPS - current
            limit_per_city = min(remaining * 2, 30)

            logger.info(f"  → Lancement : '{keyword}' @ {city} (besoin: {remaining}, limit: {limit_per_city})")
            ok, camp_id_or_err = launch_scraper(
                keyword=keyword,
                city=city,
                sector=sector,
                limit=limit_per_city,
                min_emails=0,
                campaign_name=f"Maps-{sector}-{keyword}-{city}",
                min_reviews=0,
                multi_zone=False,
            )
            if ok:
                pending_ids.add(camp_id_or_err)
                logger.info(f"    ✓ Campagne #{camp_id_or_err} lancée")
            else:
                logger.error(f"    ✗ Échec lancement: {camp_id_or_err}")

            # Attendre chaque campagne (évite conflit CDP)
            if pending_ids:
                logger.info(f"  → Attente complétion de la campagne...")
                wait_for_campaigns_to_complete(pending_ids, timeout_hours=1, poll_seconds=30)
                pending_ids.clear()

    # Attente finale
    if pending_ids:
        wait_for_campaigns_to_complete(pending_ids, timeout_hours=1, poll_seconds=30)

    final = count_maps_leads_50plus(sector)
    logger.info(f"  📊 [{sector}] Maps: {final}/{QUOTA_MAPS} leads (min {MIN_REVIEWS} avis)")
    return final


def _campaign_exists(sector: str, keyword: str, city: str) -> bool:
    """Vérifie si une campagne existe ET est encore active (pas failed/stopped)."""
    from database import get_conn
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM campagnes WHERE nom=? AND phase NOT IN ('failed','stopped','cancelled')",
            (f"Maps-{sector}-{keyword}-{city}",)
        ).fetchone()
    return row is not None


# ─── Lancement Ads ─────────────────────────────────────────────────────────────

def launch_ads_for_sector(sector_cfg: Dict):
    """Lance le pipeline Sniper Ads pour un secteur."""
    from services.sniper_runner import launch_sniper

    sector = sector_cfg["name"]
    base_keywords = sector_cfg["ads_keywords"]
    pending_ids = set()

    logger.info(f"\n{'='*70}")
    logger.info(f"📢  ADS — Secteur : {sector}")
    logger.info(f"    Quota : {QUOTA_ADS} leads")
    logger.info(f"{'='*70}")

    current = count_leads_by_sector(sector, source='ads')
    if current >= QUOTA_ADS:
        logger.info(f"  ✓ Quota déjà atteint ({current}/{QUOTA_ADS})")
        return current

    for city in BIG_CITIES:
        current = count_leads_by_sector(sector, source='ads')
        if current >= QUOTA_ADS:
            logger.info(f"  ✓ Quota Ads atteint ({current}/{QUOTA_ADS})")
            break

        remaining = QUOTA_ADS - current
        max_per_kw = max(remaining, 5)

        logger.info(f"  → Ads : {city} ({len(base_keywords)} keywords)")

        ok, msg = launch_sniper(
            keywords=base_keywords,
            country="fr",
            city=city,
            max_per_kw=max_per_kw,
            pages_per_kw=6,
            parallel_enrich=2,
            campaign_name=f"Ads-{sector}-{city}",
            min_leads=remaining,
            secteur=sector,
        )
        if ok:
            # Récupérer le campaign_id depuis la DB (le dernier créé avec ce nom)
            from database import get_conn
            with get_conn() as conn:
                row = conn.execute(
                    "SELECT id FROM campagnes WHERE nom=? ORDER BY id DESC LIMIT 1",
                    (f"Ads-{sector}-{city}",)
                ).fetchone()
                if row:
                    pending_ids.add(row[0])
            logger.info(f"    ✓ Pipeline Ads lancé pour {city}")
        else:
            logger.warning(f"    ⚠️ {msg}")

        if len(pending_ids) >= 3:
            wait_for_campaigns_to_complete(pending_ids, timeout_hours=2, poll_seconds=30)
            pending_ids.clear()

    # Attente finale
    if pending_ids:
        wait_for_campaigns_to_complete(pending_ids, timeout_hours=2, poll_seconds=30)

    # Relance sur les petites villes si nécessaire
    current = count_leads_by_sector(sector, source='ads')
    if current < QUOTA_ADS:
        logger.info(f"  → Quota non atteint ({current}/{QUOTA_ADS}), relance sur petites villes...")
        pending_ids = set()
        for city in MEDIUM_CITIES:
            current = count_leads_by_sector(sector, source='ads')
            if current >= QUOTA_ADS:
                break

            remaining = QUOTA_ADS - current

            ok, msg = launch_sniper(
                keywords=base_keywords,
                country="fr",
                city=city,
                max_per_kw=min(remaining + 3, 10),
                pages_per_kw=4,
                parallel_enrich=2,
                campaign_name=f"Ads-{sector}-{city}",
                min_leads=remaining,
                secteur=sector,
            )
            if ok:
                from database import get_conn
                with get_conn() as conn:
                    row = conn.execute(
                        "SELECT id FROM campagnes WHERE nom=? ORDER BY id DESC LIMIT 1",
                        (f"Ads-{sector}-{city}",)
                    ).fetchone()
                    if row:
                        pending_ids.add(row[0])
                logger.info(f"    ✓ Relance Ads : {city}")

            if len(pending_ids) >= 3:
                wait_for_campaigns_to_complete(pending_ids, timeout_hours=1, poll_seconds=30)
                pending_ids.clear()

        if pending_ids:
            wait_for_campaigns_to_complete(pending_ids, timeout_hours=2, poll_seconds=30)

    final = count_leads_by_sector(sector, source='ads')
    logger.info(f"  📊 [{sector}] Ads: {final}/{QUOTA_ADS} leads")
    return final


# ─── Résumé ────────────────────────────────────────────────────────────────────

def print_summary(results: Dict):
    logger.info(f"\n{'='*70}")
    logger.info(f"📋  RÉSUMÉ FINAL — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    logger.info(f"{'='*70}")

    total_maps = 0
    total_ads = 0

    for sector_name, data in results.items():
        maps_ok = "✓" if data["maps"] >= QUOTA_MAPS else "✗"
        ads_ok = "✓" if data["ads"] >= QUOTA_ADS else "✗"
        logger.info(f"  {maps_ok} {sector_name:30s} Maps: {data['maps']:>2}/{QUOTA_MAPS}  Ads: {data['ads']:>2}/{QUOTA_ADS}")
        total_maps += data["maps"]
        total_ads += data["ads"]

    logger.info(f"{'─'*70}")
    logger.info(f"  TOTAL{'':29s} Maps: {total_maps}/{QUOTA_MAPS * len(SECTORS)}  Ads: {total_ads}/{QUOTA_ADS * len(SECTORS)}")

    all_ok = all(d["maps"] >= QUOTA_MAPS and d["ads"] >= QUOTA_ADS for d in results.values())
    if all_ok:
        logger.info(f"\n  ✅ TOUS LES QUOTAS ATTEINTS !")
    else:
        logger.info(f"\n  ⚠️  Certains quotas ne sont pas atteints — voir ci-dessus.")

    logger.info(f"{'='*70}\n")


# ─── Main ──────────────────────────────────────────────────────────────────────

def main(dry_run: bool = False):
    from database import init_db, migrate_db
    init_db()
    migrate_db()
    logger.info(f"DB migrée ✓")

    logger.info(f"Démarrage de l'orchestrateur multi-secteurs")
    logger.info(f"  Maps quota  : {QUOTA_MAPS} leads/secteur (min {MIN_REVIEWS} avis)")
    logger.info(f"  Ads quota   : {QUOTA_ADS} leads/secteur")
    logger.info(f"  Secteurs    : {[s['name'] for s in SECTORS]}")
    logger.info(f"  Dry run     : {dry_run}")
    logger.info(f"{'='*70}\n")

    if dry_run:
        logger.info("🔶 DRY RUN — Aucune campagne ne sera lancée.")
        for s in SECTORS:
            current_maps = count_maps_leads_50plus(s["name"])
            current_ads = count_leads_by_sector(s["name"], source='ads')
            logger.info(f"  {s['name']:30s} Maps: {current_maps}/{QUOTA_MAPS}  Ads: {current_ads}/{QUOTA_ADS}")
        return

    os.makedirs(os.path.join(ROOT, 'data', 'logs'), exist_ok=True)

    results = {}

    for sector_cfg in SECTORS:
        sector = sector_cfg["name"]
        logger.info(f"\n{'#'*70}")
        logger.info(f"# SECTEUR : {sector}")
        logger.info(f"{'#'*70}")

        # Maps scraping
        maps_final = launch_maps_for_sector(sector_cfg)

        # Ads scraping
        ads_final = launch_ads_for_sector(sector_cfg)

        results[sector] = {"maps": maps_final, "ads": ads_final}

        logger.info(f"  [{sector}] Terminé — Maps: {maps_final}/{QUOTA_MAPS}  Ads: {ads_final}/{QUOTA_ADS}")

    print_summary(results)


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    main(dry_run=dry_run)
