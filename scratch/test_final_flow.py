import os
import sys
import logging
import asyncio

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT)

from auditeur.agents.web_analyzer import run_web_analysis

async def test_full_analysis(url):
    print(f"\n>>> TEST DU FLUX FINAL POUR : {url} <<<")
    report_dir = "data/reports/test_lead"
    os.makedirs(report_dir, exist_ok=True)
    
    try:
        results = await run_web_analysis(url, report_dir=report_dir)
        print("\n--- SYNTHÈSE DES RÉSULTATS ---")
        print(f"Mobile Score: {results.get('mobile_score')}")
        print(f"Desktop Score: {results.get('desktop_score')}")
        print(f"SEO Score: {results.get('score_seo')}")
        print(f"Mobile LCP: {results.get('mobile_lcp_ms')} ms")
        print(f"Desktop LCP: {results.get('desktop_lcp_ms')} ms")
        print(f"Screenshot Mobile: {results.get('screenshot_path')}")
        print(f"Screenshot Desktop: {results.get('screenshot_path_desktop')}")
        
        # Check files
        for f in ["preview_mobile.png", "preview_desktop.png"]:
            p = os.path.join(report_dir, f)
            if os.path.exists(p):
                print(f"[OK] Fichier {f} généré ({os.path.getsize(p)} octets)")
            else:
                print(f"[ERR] Fichier {f} MANQUANT (Optionnel — Bypassed)")
                
    except Exception as e:
        print(f"[ERR] ERREUR CRITIQUE : {e}")

if __name__ == "__main__":
    asyncio.run(test_full_analysis("https://www.google.com"))
