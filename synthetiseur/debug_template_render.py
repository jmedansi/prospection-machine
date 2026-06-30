import argparse
import sqlite3
from pathlib import Path
import jinja2
import re
from synthetiseur.generator_no_site import load_lead, resolve_sector, pick_template, SECTOR_DEFAULTS, SECTOR_COLORS

parser = argparse.ArgumentParser()
parser.add_argument('lead_id', type=int, nargs='?', default=1)
args = parser.parse_args()
lead = load_lead(args.lead_id)
sector_folder = resolve_sector(lead.get('secteur'), lead.get('category'))
template_path = pick_template(sector_folder, lead['id'])
text = template_path.read_text(encoding='utf-8')
print('TEMPLATE PATH:', template_path)
print('TEMPLATE INCLUDES NB_AVIS:', '{{NB_AVIS}}' in text)
print('TEMPLATE INCLUDES RATING:', '{{RATING}}' in text)
print('TEMPLATE INCLUDES 4.8:', '4.8' in text)

raw_nb_avis = lead.get('nb_avis') or lead.get('reviews_count')
nb_avis = str(int(raw_nb_avis)) if raw_nb_avis not in (None, '', 0) else '--'
raw_rating = lead.get('rating') or lead.get('note')
rating = f"{float(raw_rating):.1f}" if raw_rating not in (None, '') else '--'
print('lead raw rating', raw_rating, 'computed rating', rating)
print('lead raw nb_avis', raw_nb_avis, 'computed nb_avis', nb_avis)

context = {
    'NOM_ENTREPRISE': lead.get('nom'),
    'VILLE': lead.get('ville'),
    'TELEPHONE': lead.get('telephone'),
    'ADRESSE': lead.get('adresse'),
    'NB_AVIS': nb_avis,
    'RATING': rating,
    'ANNEE_CREATION': '2018',
    'LOGO_URL': '',
    'SECTEUR_TAGLINE': SECTOR_DEFAULTS.get(sector_folder, {}).get('SECTEUR_TAGLINE', ''),
    'NB_CHAMBRES': '--',
    'SPECIALITE': '',
    'SPECIALITE_MEDICALE': '',
    'TYPE_COMMERCE': '',
    'TYPE_AGENCE': '',
    'TYPE_BIJOUTERIE': '',
}
print('context', context)
jinja_env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(template_path.parent)), autoescape=False, undefined=jinja2.Undefined)
template = jinja_env.from_string(text)
html = template.render(context)
print('RENDERED INCLUDES NB_AVIS var', '{{NB_AVIS}}' in html)
print('RENDERED INCLUDES RATING var', '{{RATING}}' in html)
print('RENDERED INCLUDES 4.8', '4.8' in html)
print('RENDERED INCLUDES 9160', '9160' in html)
print('RENDERED INCLUDES 4.9', '4.9' in html)
print('RENDERED FIRST 800 CHARS:')
print(html[:800])
