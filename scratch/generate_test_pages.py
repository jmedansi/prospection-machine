# -*- coding: utf-8 -*-
"""
generate_test_pages.py - Génère des pages de test pour chaque secteur principal
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import os
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
TEMPLATES_DIR = ROOT / 'synthetiseur' / 'templates_sites'
RAPPORTS_DIR = ROOT / 'synthetiseur' / 'rapports'
RAPPORTS_DIR.mkdir(exist_ok=True)

# Données fictives par secteur pour preview
SECTOR_PREVIEWS = {
    'artisan':    {'NOM': 'Menuiserie Dubois', 'VILLE': 'Lyon', 'TEL': '04 72 00 00 00', 'template': 'artisan-hero-1-robuste.html'},
    'auto':       {'NOM': 'Garage Martin', 'VILLE': 'Marseille', 'TEL': '04 91 00 00 00', 'template': 'auto-hero-2-moderne.html'},
    'beaute':     {'NOM': 'Institut Lumière', 'VILLE': 'Bordeaux', 'TEL': '05 56 00 00 00', 'template': 'beaute-hero-1-elegant.html'},
    'bijouterie': {'NOM': 'Bijoux Élégance', 'VILLE': 'Nice', 'TEL': '04 93 00 00 00', 'template': 'bijouterie-hero-1-luxe.html'},
    'commerce':   {'NOM': 'Boutique Créations', 'VILLE': 'Nantes', 'TEL': '02 40 00 00 00', 'template': 'commerce-hero-1-boutique.html'},
    'hotellerie': {'NOM': 'Hôtel Le Charme', 'VILLE': 'Paris', 'TEL': '01 42 00 00 00', 'template': 'hotellerie-hero-2-urbain.html'},
    'immobilier': {'NOM': 'Agence Horizon', 'VILLE': 'Toulouse', 'TEL': '05 61 00 00 00', 'template': 'immobilier-hero-1-premium.html'},
    'juridique':  {'NOM': 'Cabinet Lefèvre', 'VILLE': 'Paris', 'TEL': '01 43 00 00 00', 'template': 'juridique-hero-1-institutionnel.html'},
    'restaurant': {'NOM': 'Le Bistrot du Chef', 'VILLE': 'Paris', 'TEL': '01 42 78 00 00', 'template': 'restaurant-hero-1-moderne.html'},
    'sante':      {'NOM': 'Cabinet Dr. Bernard', 'VILLE': 'Strasbourg', 'TEL': '03 88 00 00 00', 'template': 'sante-hero-1-confiance.html'},
    'sport':      {'NOM': 'CrossFit Performance', 'VILLE': 'Lille', 'TEL': '03 20 00 00 00', 'template': 'sport-hero-1-energie.html'},
}

generated = []

for sector, data in SECTOR_PREVIEWS.items():
    template_path = TEMPLATES_DIR / sector / data['template']
    if not template_path.exists():
        print(f"[SKIP] {sector} - template not found: {template_path}")
        continue

    html = template_path.read_text(encoding='utf-8')
    
    # Remplacer les variables Jinja2 avec les données test
    replacements = {
        '{{NOM_ENTREPRISE}}': data['NOM'],
        '{{NOM_ENTREPRISE_COURT}}': data['NOM'][:37] + '...' if len(data['NOM']) > 40 else data['NOM'],
        '{{VILLE}}': data['VILLE'],
        '{{TELEPHONE}}': data['TEL'],
        '{{ADRESSE}}': f"12 Rue de la Paix, {data['VILLE']}",
        '{{NB_AVIS}}': '48',
        '{{RATING}}': '4.7',
        '{{NB_CHAMBRES}}': '24',
        '{{LOGO_URL}}': '',
        '{% if LOGO_URL %}': '',
        '{% else %}': '',
        '{% endif %}': '',
        '{{SECTEUR_TAGLINE}}': sector.title(),
        '{{SPECIALITE}}': 'Expert local',
        '{{SPECIALITE_MEDICALE}}': 'Médecine générale',
        '{{TYPE_COMMERCE}}': 'Commerce',
        '{{TYPE_AGENCE}}': 'Agence',
        '{{TYPE_BIJOUTERIE}}': 'Joaillerie',
        '{{ANNEE_CREATION}}': '2018',
    }
    
    for k, v in replacements.items():
        html = html.replace(k, v)
    
    # Clean leftover Jinja blocks
    html = re.sub(r'\{%[^%]+%\}', '', html)
    html = re.sub(r'\{\{[A-Z0-9_|" \-\.]+\}\}', '--', html)
    
    out_path = RAPPORTS_DIR / f'test_{sector}.html'
    out_path.write_text(html, encoding='utf-8')
    generated.append((sector, str(out_path)))
    print(f"[OK] {sector} → {out_path.name}")

print(f"\n✓ {len(generated)} fichiers générés dans synthetiseur/rapports/")
print("\nOuvrir dans le navigateur :")
for sector, path in generated:
    print(f"  {sector}: file:///{path.replace(chr(92), '/')}")
