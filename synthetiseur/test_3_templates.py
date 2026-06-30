import re
from pathlib import Path

SAMPLE = {
    'NOM_ENTREPRISE': 'Menuiserie Dubois',
    'NOM_ENTREPRISE_COURT': 'Dubois',
    'VILLE': 'Lyon',
    'TELEPHONE': '04 78 00 00 00',
    'ADRESSE': '15 Rue des Artisans, Lyon',
    'NB_AVIS': '127',
    'RATING': '4.7',
    'ANNEE_CREATION': '2005',
    'LOGO_URL': '',
    'SECTEUR_TAGLINE': 'Artisan',
    'SPECIALITE': 'Menuiserie · Ébénisterie',
}

files = [
    ('artisan', 'artisan-hero-1-robuste.html'),
    ('auto', 'auto-hero-1-technique.html'),
    ('auto', 'auto-hero-2-moderne.html'),
]

rapports = Path('rapports')
for sector, fname in files:
    src = Path('templates_sites') / sector / fname
    html = src.read_text(encoding='utf-8')
    for k, v in SAMPLE.items():
        html = html.replace('{{' + k + '}}', str(v))
    html = re.sub(r'\{\{[A-Z0-9_"\'| \-\.]+\}\}', '--', html)
    basename = fname.replace('hero-', '').replace('.html', '')
    out = rapports / f'test_{sector}-{basename}-render.html'
    out.write_text(html, encoding='utf-8')
    print(f'OK {out.name}')
print('Done')
