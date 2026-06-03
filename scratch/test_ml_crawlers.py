# -*- coding: utf-8 -*-
import asyncio
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from enrichisseur.mentions_legales_enricher import enrichir_lead, _format_notes, _trouver_ml_playwright_sync

def test_url(url, nom="Test Company"):
    print(f"\n========================================\nTESTING URL: {url}\n========================================")
    # 1. Tester d'abord juste trouver_ml_playwright
    print("[...] Tentative de recherche ML via Playwright...")
    ml = _trouver_ml_playwright_sync(url)
    print(f"Playwright result: URL={ml.get('url')} | Error={ml.get('error')}")
    if ml.get('text'):
        print(f"Text length: {len(ml['text'])}")
        print(f"Sample: {ml['text'][:300]}")
    else:
        print("No text returned by Playwright.")

    # 2. Tester enrichir_lead global
    print("[...] Appel de enrichir_lead()...")
    res = enrichir_lead(1, url, nom)
    print("Enrichir Lead Result:")
    print(f"  Dirigeant: {res['dirigeant_prenom']} {res['dirigeant_nom']}")
    print(f"  Emails: {res['emails']}")
    print(f"  Telephones: {res['telephones']}")
    print(f"  URL Trouvee: {res['url_trouvee']}")
    notes = _format_notes(res)
    print(f"  Notes formattées: '{notes}'")

if __name__ == "__main__":
    urls = [
        "http://www.pro-sap.fr/pro-sap-formations-lyon/",
        "https://www.iri-lyon.com/",
        "https://ieseg.fr"
    ]
    for u in urls:
        test_url(u)
