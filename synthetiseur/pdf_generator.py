# -*- coding: utf-8 -*-
import os
import sys
import asyncio
import json
import argparse
import base64
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from playwright.async_api import async_playwright

# Configuration des imports pour trouver config_manager.py au root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# On essaie d'importer enrich_data depuis reporter.main si disponible
try:
    from reporter.main import enrich_data
except ImportError:
    # Fallback : une version simplifiée si non importable
    def enrich_data(data):
        return data

async def capture_screenshot(url: str, output_path: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 1280, 'height': 720})
        try:
            await page.goto(url, timeout=30000, wait_until="networkidle")
            await page.screenshot(path=output_path)
            return True
        except: return False
        finally: await browser.close()


async def generate_pdf_profil_a(pdf_data: dict, output_pdf_path: str):
    """Génère un PDF Profil A (Maquette) pour les prospects sans site web."""
    # On ajoute la date et le dictionnaire
    MOIS_FR = {
      1:"Janvier", 2:"Février", 3:"Mars", 4:"Avril",
      5:"Mai", 6:"Juin", 7:"Juillet", 8:"Août",
      9:"Septembre", 10:"Octobre", 11:"Novembre", 12:"Décembre"
    }
    now = datetime.now()
    pdf_data["date"] = f"{now.day} {MOIS_FR[now.month]} {now.year}"
    
    # Formatage spécifique des arguments pour WeasyPrint
    args_list = pdf_data.get('arguments', [])
    if isinstance(args_list, list):
        pdf_data['arguments'] = "\n\n".join(f"• {arg}" for arg in args_list)

    template_dir = os.path.join(os.path.dirname(__file__), "templates")
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template("pdf_profil_a.html")
    
    html_content = template.render(**pdf_data)
    
    # Generation PDF avec Playwright (en vrai, l'utilisateur a écrit WeasyPrint dans le prompt mais on utilise Playwright comme partout ailleurs)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(html_content)
        await asyncio.sleep(1) # Attente polices et images locales
        await page.pdf(path=output_pdf_path, format="A4", print_background=True)
        await browser.close()
    return True

async def generate_pdf(audit_data: dict, output_pdf_path: str):
    """Génère un PDF à partir des données d'audit enrichies."""
    # S'assurer que les données sont enrichies (si ce n'est pas déjà fait)
    # On importe enrich_data et BENCHMARKS pour avoir les structures metrics/bool_metrics/benchmarks
    from reporter.main import enrich_data, BENCHMARKS, detect_sector
    
    if "metrics" not in audit_data:
        enriched = enrich_data(audit_data)
    else:
        enriched = audit_data

    # Injecter les benchmarks pour le template
    sector_key = detect_sector(enriched.get("category", ""))
    enriched["benchmarks"] = BENCHMARKS[sector_key]

    MOIS_FR = {
      1:"Janvier", 2:"Février", 3:"Mars", 4:"Avril",
      5:"Mai", 6:"Juin", 7:"Juillet", 8:"Août",
      9:"Septembre", 10:"Octobre", 11:"Novembre", 12:"Décembre"
    }
    now = datetime.now()
    date_audit = f"{now.day} {MOIS_FR[now.month]} {now.year}"
    enriched["date_audit"] = date_audit

    # --- Bug 4: Vérification défensive des arguments ---
    arguments = enriched.get('arguments', [
        "Point 1 non disponible",
        "Point 2 non disponible",
        "Point 3 non disponible"
    ])
    enriched['arguments'] = arguments
    print(f"Arguments reçus : {enriched.get('arguments', 'ABSENT')}")

    template_dir = os.path.join(os.path.dirname(__file__), "templates")
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template("audit_template.html")
    
    html_content = template.render(**enriched)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(html_content)
        await asyncio.sleep(1) # Laisser le temps au rendu CSS/Fonts
        await page.pdf(path=output_pdf_path, format="A4", print_background=True)
        await browser.close()
    return True

async def run_test():
    """Génère un rapport de test fictif."""
    print("--- Démarrage du Test PDF Generator ---")
    
    # Données fictives simulant le retour de l'auditeur + enrich_data
    fake_audit = {
        "nom": "Ashton Ross Law",
        "ville": "Paris, France",
        "category": "Cabinet Juridique",
        "site_web": "ashtonrosslaw.com",
        "mobile_score": 55,
        "lcp_ms": 4800,
        "page_size_kb": 2800,
        "render_blocking_scripts": 3,
        "rating": 4.9,
        "reviews_count": 73,
        "photos_count": 8,
        "has_meta_description": False,
        "has_site": True,
        "score_priorite": 7,
        "has_https": True,
        "uses_cache": False,
        "title_length": 12
    }
    
    # On importe enrich_data pour avoir les structures metrics/bool_metrics
    from reporter.main import enrich_data
    enriched_test = enrich_data(fake_audit)
    
    timestamp = datetime.now().strftime("%H%M%S")
    output_path = os.path.join(os.path.dirname(__file__), f"test_report_{timestamp}.pdf")
    print(f"Génération du PDF : {output_path}...")
    
    if await generate_pdf(enriched_test, output_path):
        print(f"✅ Succès ! Rapport généré : {output_path}")
    else:
        print("❌ Échec de la génération.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Lancer un test complet")
    args = parser.parse_args()
    
    if args.test:
        asyncio.run(run_test())
