import sqlite3
import re
from pathlib import Path

import jinja2

ROOT = Path(__file__).parent
DB_PATH = ROOT / 'data' / 'prospection.db'

HOTEL_SQL = '''
SELECT id, nom, secteur, category, ville, telephone, adresse, nb_avis
FROM leads_bruts
WHERE lower(secteur) LIKE ?
   OR lower(category) LIKE ?
   OR lower(secteur) LIKE ?
   OR lower(category) LIKE ?
   OR lower(secteur) LIKE ?
   OR lower(category) LIKE ?
ORDER BY id ASC
LIMIT 1
'''

REPLACEMENTS = {
    '{{NOM_ENTREPRISE}}':       None,
    '{{VILLE}}':                None,
    '{{TELEPHONE}}':            None,
    '{{ADRESSE}}':              None,
    '{{NB_AVIS}}':              None,
    '{{ANNEE_CREATION}}':       '2018',
    '{{LOGO_URL}}':             None,
    '{{SECTEUR_TAGLINE}}':      'Hôtellerie & Hébergement',
    '{{NB_CHAMBRES}}':          '--',
    '{{SPECIALITE}}':           'Expertise Locale',
    '{{SPECIALITE_MEDICALE}}':  'Généraliste',
    '{{TYPE_COMMERCE}}':        'Boutique',
    '{{TYPE_AGENCE}}':          'Agence Immobilière',
    '{{TYPE_BIJOUTERIE}}':      'Joaillerie',
}

HOTELLERIE_TEMPLATES = [
    'hotellerie-hero-1-luxe.html',
    'hotellerie-hero-2-urbain.html',
]
TEMPLATE_BASE_COLORS = {
    'hotellerie-hero-1-luxe.html': '#b5924c',
    'hotellerie-hero-2-urbain.html': '#e9c46a',
}
TEMPLATE_COLOR = '#b5924c'


def select_hotel_lead():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    params = ('%hotel%', '%hotel%', '%hôtel%', '%hôtel%', '%hotel%', '%hôtel%')
    cur.execute(HOTEL_SQL, params)
    row = cur.fetchone()
    conn.close()
    if not row:
        raise RuntimeError('Aucun lead hôtelier trouvé dans leads_bruts.')
    keys = ['id','nom','secteur','category','ville','telephone','adresse','nb_avis']
    lead = dict(zip(keys, row))
    lead['logo_url'] = 'https://images.unsplash.com/photo-1599305445671-ac291c95aba9?w=100&h=100&fit=crop'
    return lead



def render_template(lead: dict):
    lead_id = lead['id'] or 0
    template_filename = HOTELLERIE_TEMPLATES[lead_id % len(HOTELLERIE_TEMPLATES)]
    template_path = ROOT / 'synthetiseur' / 'templates_sites' / 'hotellerie' / template_filename
    if not template_path.exists():
        raise FileNotFoundError(f'Template introuvable: {template_path}')

    template_text = template_path.read_text(encoding='utf-8')
    nom_complet = lead.get('nom') or 'Votre Entreprise'
    nom_affiche = (nom_complet[:37] + '...') if len(nom_complet) > 40 else nom_complet
    nb_avis = str(lead.get('nb_avis') or lead.get('reviews_count') or 0)

    jinja_context = {
        'NOM_ENTREPRISE': nom_affiche,
        'VILLE': lead.get('ville') or 'Votre Ville',
        'TELEPHONE': lead.get('telephone') or 'Contactez-nous',
        'ADRESSE': lead.get('adresse') or '',
        'NB_AVIS': nb_avis,
        'ANNEE_CREATION': '2018',
        'LOGO_URL': lead.get('logo_url') or '',
        'SECTEUR_TAGLINE': 'Hôtellerie & Hébergement',
        'NB_CHAMBRES': '--',
        'SPECIALITE': 'Expertise Locale',
        'SPECIALITE_MEDICALE': 'Généraliste',
        'TYPE_COMMERCE': 'Boutique',
        'TYPE_AGENCE': 'Agence Immobilière',
        'TYPE_BIJOUTERIE': 'Joaillerie',
        'screenshot_desktop': None,
        'screenshot_mobile': None,
    }

    jinja_loader = jinja2.FileSystemLoader(str(ROOT / 'synthetiseur' / 'templates_sites' / 'hotellerie'))
    jinja_env = jinja2.Environment(loader=jinja_loader, autoescape=False)
    template = jinja_env.from_string(template_text)
    html = template.render(jinja_context)

    html = re.sub(r'\{\{[A-Z0-9_]+\}\}', '--', html)

    base_color = TEMPLATE_BASE_COLORS.get(template_filename)
    if base_color:
        html = html.replace(base_color, TEMPLATE_COLOR)

    if lead.get('logo_url'):
        html = html.replace('display:none; /* Python met display:block si logo dispo */', 'display:block;')
        html = html.replace('display:block; /* Nom texte — affiché par défaut */', 'display:none;')

    output_path = ROOT / 'synthetiseur' / f'tmp_lead_{lead_id}_hotellerie.html'
    output_path.write_text(html, encoding='utf-8')
    return output_path, template_filename


def main():
    lead = select_hotel_lead()
    path, template = render_template(lead)
    print('Lead ID      :', lead['id'])
    print('Nom          :', lead['nom'])
    print('Secteur      :', lead['secteur'] or lead['category'])
    print('Template     :', template)
    print('HTML saved to:', path)
    print('---')
    print('First lines of generated HTML:')
    with open(path, encoding='utf-8') as f:
        for _ in range(20):
            line = f.readline()
            if not line:
                break
            print(line.rstrip())


if __name__ == '__main__':
    main()
