# -*- coding: utf-8 -*-
import asyncio
import json
import os
import sys

# Ajout du dossier parent pour config_manager
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import run_tech_audit, check_daily_reset
from agents.web_analyzer import run_web_analysis
import config_manager

async def test_static_first():
    print("--- Démarrage du Test Agent Auditeur (Static-First) ---")
    
    # 0. Initialisation (rotation, reset)
    check_daily_reset()
    
    # 1. Diagnostic des clés
    config = config_manager.get_config()
    print("=== Diagnostic des clés disponibles ===")
    for k, v in config.items():
        if isinstance(v, str) and len(v) > 4:
            print(f"  {k} : {v[:4]}...{v[-4:]}")
    print("=" * 40)
    
    test_leads = [
        {"nom": "Google", "ville": "Mountain View", "site": "https://google.com"},
        {"nom": "Le Perdu", "ville": "Paris", "site": "https://perdu.com"},
        {"nom": "L'Étoile du Mali", "ville": "Cotonou", "site": "https://www.letoiledumali.com"}
    ]
    
    for lead in test_leads:
        print(f"\n--- Test de : {lead['nom']} ({lead['site']}) ---")
        try:
            # L'audit web technique
            result = run_web_analysis(lead["site"])
            
            # Affichage du JSON complet pour vérification
            print("\n[RESULTATS TECHNIQUES EXTRAITS]")
            print(f"  > Score Mobile  : {result.get('mobile_score')}/100")
            print(f"  > Score Desktop : {result.get('desktop_score')}/100")
            print(f"  > Score Tablet  : {result.get('tablet_score')}/100")
            print(f"  > LCP Mobile    : {result.get('mobile_lcp_ms')}ms")
            print(f"  > H1 Count      : {result.get('h1_count')}")
            print(f"  > Meta Desc     : {'✅' if result.get('has_meta_description') else '❌'}")
            
        except Exception as e:
            print(f"[ERREUR] Échec du test pour {lead['nom']}: {e}")
            
        print("\nPause de 3s pour les quotas...")
        await asyncio.sleep(3)

if __name__ == "__main__":
    asyncio.run(test_static_first())
