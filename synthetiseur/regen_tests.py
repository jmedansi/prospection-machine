"""Regenerate all test_*.html files from updated source templates + index page."""
import re
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent / 'templates_sites'
RAPPORTS_DIR = Path(__file__).parent / 'rapports'

SAMPLE_DATA = {
    'NOM_ENTREPRISE': 'Le Bistrot du Chef',
    'NOM_ENTREPRISE_COURT': 'Le Bistrot du Chef',
    'VILLE': 'Paris',
    'TELEPHONE': '01 42 78 00 00',
    'ADRESSE': '12 Rue de la Paix, Paris',
    'NB_AVIS': '48',
    'RATING': '4.8',
    'ANNEE_CREATION': '2018',
    'LOGO_URL': '',
    'SECTEUR_TAGLINE': 'Restaurant',
    'NB_CHAMBRES': '24',
    'SPECIALITE': 'Expert local',
    'SPECIALITE_MEDICALE': 'Médecine générale · Pédiatrie',
    'TYPE_COMMERCE': 'Boutique',
    'TYPE_AGENCE': 'Agence web',
    'TYPE_BIJOUTERIE': 'Joaillerie',
}

SECTOR_FILES = {
    'restaurant': ['restaurant-hero-1-moderne.html', 'restaurant-hero-2-chaleureux.html'],
    'hotellerie': ['hotellerie-hero-1-luxe.html', 'hotellerie-hero-2-urbain.html'],
    'sante': ['sante-hero-1-confiance.html', 'sante-hero-2-lumineux.html'],
    'artisan': ['artisan-hero-1-robuste.html', 'artisan-hero-2-expertise.html'],
    'auto': ['auto-hero-1-technique.html', 'auto-hero-2-moderne.html'],
    'beaute': ['beaute-hero-1-elegant.html', 'beaute-hero-2-moderne.html'],
    'bijouterie': ['bijouterie-hero-1-luxe.html', 'bijouterie-hero-2-tendance.html'],
    'commerce': ['commerce-hero-1-boutique.html', 'commerce-hero-2-artisan.html'],
    'default': ['default-hero-1-professionnel.html', 'default-hero-2-chaleureux.html'],
    'immobilier': ['immobilier-hero-1-premium.html', 'immobilier-hero-2-moderne.html'],
    'juridique': ['juridique-hero-1-institutionnel.html', 'juridique-hero-2-moderne.html'],
    'sport': ['sport-hero-1-energie.html', 'sport-hero-2-coach.html'],
    'comptable': ['comptable-hero-1-institutionnel.html', 'comptable-hero-2-moderne.html'],
    'ong': ['ong-hero-1-mission.html', 'ong-hero-2-impact.html'],
    'microfinance': ['microfinance-hero-1-confiance.html', 'microfinance-hero-2-moderne.html'],
}

SECTOR_LABELS = {
    'restaurant': 'Restauration',
    'hotellerie': 'Hôtellerie',
    'sante': 'Santé',
    'artisan': 'Artisan',
    'auto': 'Automobile',
    'beaute': 'Beauté',
    'bijouterie': 'Bijouterie',
    'commerce': 'Commerce',
    'default': 'Default',
    'immobilier': 'Immobilier',
    'juridique': 'Juridique',
    'sport': 'Sport',
    'comptable': 'Comptable',
    'ong': 'ONG',
    'microfinance': 'Microfinance',
}

def render_template(template_path: Path, data: dict) -> str:
    html = template_path.read_text(encoding='utf-8')
    for key, value in data.items():
        html = html.replace(f'{{{{{key}}}}}', str(value))
    html = re.sub(r'\{\{[A-Z0-9_|" \-\.]+\}\}', '--', html)
    return html

generated = []
for sector, files in SECTOR_FILES.items():
    for fname in files:
        src = TEMPLATES_DIR / sector / fname
        if not src.exists():
            print(f"  SKIP {src} (not found)")
            continue
        html = render_template(src, SAMPLE_DATA)
        # Use hero-1 and hero-2 suffix
        suffix = '1' if 'hero-1' in fname else '2'
        out = RAPPORTS_DIR / f'test_{sector}-{suffix}.html'
        out.write_text(html, encoding='utf-8')
        label = SECTOR_LABELS.get(sector, sector)
        generated.append((sector, suffix, label, out.name))
        print(f"  OK   {out.name}")

# Generate index page
index_html = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tests Templates — UI/UX Pro Max</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',system-ui,sans-serif;background:#0a0a0a;color:#fff;padding:2rem}
h1{font-size:1.5rem;margin-bottom:.5rem}
.sub{color:rgba(255,255,255,.5);margin-bottom:2rem;font-size:.9rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:1rem}
.card{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);border-radius:12px;padding:1.25rem;transition:all .2s}
.card:hover{background:rgba(255,255,255,.08);border-color:rgba(255,255,255,.15)}
.sector{font-weight:700;font-size:1rem;margin-bottom:.75rem;color:#e9c46a}
.links{display:flex;gap:.5rem}
.links a{display:inline-block;padding:.4rem .8rem;background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.15);border-radius:6px;color:#fff;text-decoration:none;font-size:.78rem;font-weight:500;transition:all .2s}
.links a:hover{background:#fff;color:#0a0a0a}
</style>
</head>
<body>
<h1>UI/UX Pro Max — Templates Test</h1>
<p class="sub">26 templates across 13 sectors · Glassmorphism nav · Styled buttons · Responsive</p>
<div class="grid">
"""

for sector, suffix, label, fname in sorted(generated, key=lambda x: x[0]):
    index_html += f"""<div class="card">
<div class="sector">{label}</div>
<div class="links">
<a href="{fname}" target="_blank">Hero {suffix}</a>
</div>
</div>
"""

index_html += """</div>
</body>
</html>"""

(RAPPORTS_DIR / 'test_index.html').write_text(index_html, encoding='utf-8')
print(f"\n  OK   test_index.html (index page)")
print(f"\n{len(generated)} files + index regenerated")
