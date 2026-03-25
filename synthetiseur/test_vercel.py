# -*- coding: utf-8 -*-
"""
synthetiseur/test_vercel.py — Test du module vercel_publisher.
"""
import os
import sys

# Ajout du dossier racine au PATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from synthetiseur.vercel_publisher import publish_rapport

# Données de test réelles basées sur Clinique Santé Plus (car les fichiers existent)
audit_test = {
    "nom":           "Hôtel de Paris",
    "ville":         "Paris",
    "sector_label":  "Hôtellerie",
    "rating":        4.5,
    "reviews_count": 128,
    "telephone":     "+33 1 23 45 67 89",
    "arguments": [
        "Votre site actuel est lent (8,2s de chargement).",
        "Vous perdez 40% de vos clients sur mobile.",
        "Vos concurrents directs ont déjà une interface moderne."
    ]
}

# Utilisation des fichiers existants pour le test (si possible) ou vides
screenshots_test = {
    "screenshot_desktop": "mockups/screenshots/Clinique_Santé_Plus_desktop.png",
    "screenshot_mobile":  "mockups/screenshots/Clinique_Santé_Plus_mobile.png",
}

print("\n🚀 Lancement du test Vercel...")

try:
    url = publish_rapport(audit_test, screenshots_test)
    print(f"\n✅ audit.incidenx.com/hotel-de-paris — OK")
    print(f"🔗 URL accessible : {url}")
except Exception as e:
    print(f"\n❌ ÉCHEC DU TEST")
    print(f"Erreur API Vercel : {e}")
    print("\nDiagnostic possible :")
    print("- Vérifie VERCEL_TOKEN dans .env")
    print("- Vérifie VERCEL_PROJECT_ID et VERCEL_PROJECT_NAME")
    print("- Vérifie la connexion internet")
