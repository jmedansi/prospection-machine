# -*- coding: utf-8 -*-
"""
Test rapide de l'extracteur d'annonces Google.
Usage : python scraper/sniper/test_ads.py --keyword "agence seo" --country fr --pages 10
"""
import sys
import os

if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

import asyncio
import argparse
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


async def run_test(keyword: str, country: str, max_pages: int):
    from scraper.sniper.ads_extractor import (
        _extract_from_google, _get_cdp_browser, _MAX_PAGES_SAFETY
    )

    print(f"\n{'='*60}")
    print(f"TEST ADS EXTRACTOR")
    print(f"  Keyword : {keyword}")
    print(f"  Pays    : {country}")
    print(f"  Pages max : {max_pages}")
    print(f"  Démarré : {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*60}\n")

    browser = await _get_cdp_browser()
    if browser is None:
        print("[ERREUR] Chrome non accessible sur le port CDP.")
        print("  → Lance Chrome avec --remote-debugging-port=9222")
        return

    ctx = browser.contexts[0]
    page = await ctx.new_page()
    t0 = time.time()

    try:
        domains, page, was_blocked = await _extract_from_google(
            page, browser, keyword, country,
            max_per_kw=9999,
            pages_per_kw=max_pages,
        )
    except Exception as e:
        import traceback
        print(f"\n[ERREUR CRITIQUE]\n{traceback.format_exc()}")
        domains, was_blocked = [], True
    finally:
        try:
            await page.close()
        except Exception:
            pass

    elapsed = time.time() - t0

    print(f"\n{'='*60}")
    print(f"RÉSUMÉ")
    print(f"  Leads uniques trouvés : {len(domains)}")
    print(f"  Bloqué (captcha/err)  : {was_blocked}")
    print(f"  Durée totale          : {elapsed:.1f}s")
    if domains:
        print(f"\n  Liste des annonceurs :")
        for i, d in enumerate(domains, 1):
            print(f"    {i:>3}. {d}")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--keyword", default="agence seo", help="Mot-clé à tester")
    parser.add_argument("--country", default="fr", choices=["fr", "ch", "be", "lu"])
    parser.add_argument("--pages", type=int, default=10, help="Nombre de pages max")
    args = parser.parse_args()

    asyncio.run(run_test(args.keyword, args.country, args.pages))


if __name__ == "__main__":
    main()
