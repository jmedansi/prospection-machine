import os
import sys
import time
import requests
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT)

from auditeur.agents.web_analyzer import run_pagespeed, measure_local_speed

def compare_scores(url):
    print(f"\n===== COMPARAISON POUR : {url} =====")
    
    # 1. PageSpeed API Score
    print("Appel PageSpeed API...")
    ps_start = time.time()
    ps_result = run_pagespeed(url, strategy="mobile")
    ps_duration = time.time() - ps_start
    
    # 2. Local Fallback Score
    print("Appel Mesure Locale (Fallback)...")
    local_start = time.time()
    local_metrics = measure_local_speed(url)
    local_duration = time.time() - local_start
    
    # Calcul manuel du score local comme dans web_analyzer.py
    penalty_ms = 1500
    lcp_fr = max(800, local_metrics["lcp_ms"] - penalty_ms)
    
    if lcp_fr <= 2500:
        local_score = 90 + max(0, 10 - (lcp_fr / 250))
    elif lcp_fr <= 6000:
        local_score = 50 + (6000 - lcp_fr) / 100
    else:
        local_score = max(5, 50 - (lcp_fr - 6000) / 200)
    local_score = round(min(99, local_score))
    
    print("\n--- RÉSULTATS ---")
    print(f"PAGESPEED API :")
    print(f"  - Score: {ps_result.get('mobile_score')}")
    print(f"  - LCP: {ps_result.get('mobile_lcp_ms')} ms")
    print(f"  - Temps d'analyse: {ps_duration:.1f}s")
    print(f"  - Erreur: {ps_result.get('pagespeed_error')}")
    
    print(f"\nNOTRE AUDITEUR (Local Corrigé) :")
    print(f"  - Score: {local_score}")
    print(f"  - LCP Brut (Bénin): {local_metrics['lcp_ms']:.0f} ms")
    print(f"  - LCP Estimé (France): {lcp_fr:.0f} ms")
    print(f"  - Temps d'analyse: {local_duration:.1f}s")
    
    diff = local_score - (ps_result.get('mobile_score') or 0)
    print(f"\nDifférence de score: {diff:+}")

if __name__ == "__main__":
    compare_scores("https://www.google.com")
    compare_scores("https://www.lemonde.fr")
    compare_scores("https://www.cdiscount.com") # Souvent lourd
