# -*- coding: utf-8 -*-
"""
Temporary runner for Google Ads lead collection.
Use this file only for the current operation, then delete it.
"""

import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scraper.sniper.overnight_ads_pipeline import phase1_scrape, logger


async def main():
    logger.info("=== TEMPORARY ADS LEADS RUNNER ===")
    logger.info("Lancement de la recherche Google Ads...")
    all_leads = await phase1_scrape()

    total = sum(len(ids) for ids in all_leads.values())
    logger.info(f"Total leads insérés : {total}")
    for secteur, ids in all_leads.items():
        logger.info(f"  {secteur}: {len(ids)} leads")

    logger.info("Terminé. Ce script est temporaire, supprime-le après usage.")


if __name__ == "__main__":
    asyncio.run(main())
