# -*- coding: utf-8 -*-
"""
generator_no_site.py
====================
Génère un rapport HTML Profil A pour un lead sans site web.

Workflow :
  1. Charge le lead depuis leads_bruts (avec son logo_url et secteur)
  2. Détermine le bon template sectoriel
  3. Rend le template Jinja2 avec les vraies données du prospect
  4. Sauvegarde le fichier HTML dans synthetiseur/rapports/
  5. Retourne le chemin + le texte WhatsApp prêt à envoyer

Usage :
  from synthetiseur.generator_no_site import generate_report_no_site
  result = generate_report_no_site(lead_id=42)
  print(result['html_path'])
  print(result['whatsapp_message'])

  Ou en CLI :
  python -m synthetiseur.generator_no_site --lead-id 42
  python -m synthetiseur.generator_no_site --lead-id 42 --open
"""

import io
import os
import re
import sqlite3
import sys
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Optional

import jinja2

# Force UTF-8 output on Windows
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ── Chemins ────────────────────────────────────────────────────────────────────
ROOT         = Path(__file__).parent.parent          # D:/prospection-machine
DB_PATH      = ROOT / 'data' / 'prospection.db'
TEMPLATES_DIR = Path(__file__).parent / 'templates_sites'
RAPPORTS_DIR  = Path(__file__).parent / 'rapports'
RAPPORTS_DIR.mkdir(exist_ok=True)

# ── Mapping secteur → dossier templates ────────────────────────────────────────
SECTOR_MAP = {
    # Clés DB → dossier dans templates_sites
    'hotellerie':  'hotellerie',
    'hotel':       'hotellerie',
    'hôtel':       'hotellerie',
    'restaurant':  'restaurant',
    'restauration':'restaurant',
    'boulangerie': 'restaurant',
    'beaute':      'beaute',
    'beauté':      'beaute',
    'coiffure':    'beaute',
    'salon':       'beaute',
    'sante':       'sante',
    'santé':       'sante',
    'médecin':     'sante',
    'dentiste':    'sante',
    'clinique':    'sante',
    'pharmacie':   'sante',
    'juridique':   'juridique',
    'avocat':      'juridique',
    'notaire':     'juridique',
    'immobilier':  'immobilier',
    'artisan':     'artisan',
    'plombier':    'artisan',
    'électricien': 'artisan',
    'menuisier':   'artisan',
    'auto':        'auto',
    'garage':      'auto',
    'automobile':  'auto',
    'bijouterie':  'bijouterie',
    'bijoux':      'bijouterie',
    'commerce':    'commerce',
    'boutique':    'commerce',
    'magasin':     'commerce',
    'sport':       'sport',
    'fitness':     'sport',
    'comptable':   'comptable',
    'expertise comptable': 'comptable',
    'coach':       'sport',
    'education':   'education',
    'éducation':   'education',
    'formation':   'education',
    'école':       'education',
    'ecole':       'education',
    'evenementiel':'evenementiel',
    'événementiel':'evenementiel',
    'mariage':     'evenementiel',
    'microfinance':'microfinance',
    'ong':         'ong',
    'association': 'ong',
    'humanitaire': 'ong',
    'asso':        'ong',
}

# Couleurs d'accent par secteur (même mapping qu'inject_profil_a.py)
SECTOR_COLORS = {
    'artisan':    '#e07b39',
    'auto':       '#e63946',
    'beaute':     '#c9a0a0',
    'bijouterie': '#d4af37',
    'commerce':   '#e76f51',
    'default':    '#3d5a80',
    'hotellerie': '#b5924c',
    'immobilier': '#1a3c34',
    'juridique':  '#1e3a5f',
    'restaurant': '#c8a96e',
    'sante':      '#0077b6',
    'sport':      '#00c896',
    'comptable':  '#1a5276',
    'education':  '#c0392b',
    'evenementiel':'#d4af37',
    'microfinance':'#1a5276',
    'ong':         '#2ecc71',
}

# Variables Jinja par secteur (valeurs par défaut métier)
SECTOR_DEFAULTS = {
    'hotellerie':  {'SECTEUR_TAGLINE': 'Hôtellerie & Hébergement', 'NB_CHAMBRES': '--'},
    'restaurant':  {'SECTEUR_TAGLINE': 'Restauration & Gastronomie', 'TYPE_COMMERCE': 'Restaurant'},
    'beaute':      {'SECTEUR_TAGLINE': 'Beauté & Bien-être', 'TYPE_COMMERCE': 'Institut'},
    'sante':       {'SECTEUR_TAGLINE': 'Santé & Médical', 'SPECIALITE_MEDICALE': 'Généraliste'},
    'juridique':   {'SECTEUR_TAGLINE': 'Cabinet Juridique', 'SPECIALITE': 'Droit des affaires'},
    'immobilier':  {'SECTEUR_TAGLINE': 'Immobilier', 'TYPE_AGENCE': 'Agence Immobilière'},
    'artisan':     {'SECTEUR_TAGLINE': 'Artisanat & Métiers', 'SPECIALITE': 'Artisan qualifié'},
    'auto':        {'SECTEUR_TAGLINE': 'Automobile & Services', 'TYPE_COMMERCE': 'Garage'},
    'bijouterie':  {'SECTEUR_TAGLINE': 'Joaillerie & Bijouterie', 'TYPE_BIJOUTERIE': 'Joaillerie'},
    'commerce':    {'SECTEUR_TAGLINE': 'Commerce Local', 'TYPE_COMMERCE': 'Boutique'},
    'sport':       {'SECTEUR_TAGLINE': 'Sport & Coaching', 'SPECIALITE': 'Coach sportif'},
    'comptable':   {'SECTEUR_TAGLINE': 'Expertise Comptable & Gestion', 'TYPE_COMMERCE': 'Cabinet Comptable'},
    'education':   {'SECTEUR_TAGLINE': 'Éducation & Formation'},
    'evenementiel':{'SECTEUR_TAGLINE': 'Événementiel & Réception', 'TYPE_COMMERCE': 'Organisateur'},
    'microfinance':{'SECTEUR_TAGLINE': 'Microfinance & Services Financiers'},
    'ong':         {'SECTEUR_TAGLINE': 'ONG & Association'},
    'default':     {'SECTEUR_TAGLINE': 'Commerce Local', 'TYPE_COMMERCE': 'Commerce'},
}


def format_rating(value):
    try:
        if value is None or value == "":
            return None
        return f"{float(value):.1f}"
    except Exception:
        return None


def force_logo_display(html: str) -> str:
    """Obsolète — on n'affiche plus de logo image, uniquement le nom texte."""
    return html  # no-op


def ensure_responsive(html: str) -> str:
    """Injecte meta viewport et un minimum de CSS responsive sans casser le layout natif du template."""
    lower = html.lower()
    meta = '<meta name="viewport" content="width=device-width, initial-scale=1">'
    if '<meta name="viewport"' not in lower and '</head>' in html:
        html = html.replace('</head>', meta + '\n' + '</head>', 1)

    responsive_css = (
        '<style id="incidenx-responsive-override">'
        'html,body{width:100%;overflow-x:hidden;}'
        '*,*::before,*::after{box-sizing:border-box;}'
        'img{max-width:100%!important;height:auto!important;}'
        '.nav-logo-img{max-height:60px;width:auto;}'
        '@media(max-width:767px){'
        '.hero-right{display:none!important;}'
        '.hero-footer{display:none!important;}'
        '}'
        '@media(min-width:768px) and (max-width:1024px){'
        '.hero{grid-template-columns:55% 45%;}'
        '}'
        '</style>'
    )
    if '</head>' in html:
        html = html.replace('</head>', responsive_css + '</head>', 1)
    return html


def replace_static_rating(html: str, rating: str) -> str:
    if not rating:
        return html

    replacements = [
        (r'Note\s+4\.8\s*/\s*5', f'Note {rating}/5'),
        (r'Note\s+4\.8(?![0-9A-Za-z])', f'Note {rating}'),
        (r'4\.8\s*/\s*5', f'{rating}/5'),
        (r'4\.8\s*★', f'{rating}★'),
        (r'(?<![0-9A-Za-z])4\.8(?![0-9A-Za-z])', rating),
        (r'>\s*4\.8\s*<', f'>{rating}<'),
    ]

    for pattern, replacement in replacements:
        html = re.sub(pattern, replacement, html)

    return html


def remove_logo_and_mockup(html: str, logo_url: str = '') -> str:
    """Supprime la section mockup et nettoie les placeholders résiduels."""
    # Supprimer uniquement le bloc de mockup généré suivant le commentaire de section
    html = re.sub(
        r'<!--\s*Section mockup screenshots\s*-->\s*<section[^>]*\bclass=["\']?[^"\'>]*\bprofil-a-preview-section\b[^"\'>]*["\']?[^>]*>.*?</section>',
        '',
        html,
        flags=re.S,
    )
    if not logo_url:
        html = re.sub(r'<img[^>]*\bclass=["\']?[^"\'>]*\bnav-logo-img\b[^"\'>]*["\']?[^>]*>', '', html, flags=re.S)
    html = re.sub(r'\{\{\s*screenshot_desktop\s*\}\}', '', html)
    html = re.sub(r'\{\{\s*screenshot_mobile\s*\}\}', '', html)
    html = re.sub(r'\{\{\s*NB_AVIS\s*\}\}', '--', html)
    html = re.sub(r'\{\{\s*RATING\s*\}\}', '--', html)
    html = re.sub(r'\n{3,}', '\n\n', html)
    return html


def resolve_sector(secteur: Optional[str], category: Optional[str]) -> str:
    """Détermine le dossier de template à utiliser."""
    for raw in [secteur, category]:
        if not raw:
            continue
        key = raw.lower().strip()
        if key in SECTOR_MAP:
            return SECTOR_MAP[key]
        # Recherche partielle
        for k, v in SECTOR_MAP.items():
            if k in key or key in k:
                return v
    return 'default'


def pick_template(sector_folder: str, lead_id: int) -> Path:
    """Choisit un template dans le dossier du secteur (round-robin sur l'id)."""
    folder = TEMPLATES_DIR / sector_folder

    candidates = sorted([
        f for f in folder.iterdir()
        if f.is_file() and f.suffix == '.html'
    ])
    if not candidates:
        folder = TEMPLATES_DIR / 'default'
        candidates = sorted([f for f in folder.iterdir() if f.is_file() and f.suffix == '.html'])
    if not candidates:
        raise FileNotFoundError(f"Aucun template trouvé dans {folder}")
    return candidates[lead_id % len(candidates)]


def load_lead(lead_id: int) -> dict:
    """Charge un lead depuis leads_bruts."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM leads_bruts WHERE id = ?", (lead_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise ValueError(f"Lead introuvable : id={lead_id}")
    return dict(row)


def load_lead_no_site(limit: int = 1, offset: int = 0) -> list[dict]:
    """Charge des leads sans site web depuis leads_bruts."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM leads_bruts
        WHERE (site_web IS NULL OR site_web = '' OR site_web = 'SANS SITE')
        ORDER BY id ASC
        LIMIT ? OFFSET ?
    """, (limit, offset))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def render_html(lead: dict) -> tuple[str, Path]:
    """
    Rend le template HTML pour ce lead.
    Retourne (html_content, output_path).
    """
    lead_id    = lead['id']
    nom        = lead.get('nom') or 'Votre Entreprise'
    nom_court  = (nom[:37] + '...') if len(nom) > 40 else nom
    secteur_db = lead.get('secteur') or ''
    category   = lead.get('category') or ''

    # Résolution secteur
    sector_folder = resolve_sector(secteur_db, category)
    accent_color  = SECTOR_COLORS.get(sector_folder, SECTOR_COLORS['default'])
    sector_defs   = SECTOR_DEFAULTS.get(sector_folder, SECTOR_DEFAULTS['default'])

    # Sélection du template
    template_path = pick_template(sector_folder, lead_id)

    # Lecture brute
    template_text = template_path.read_text(encoding='utf-8')

    # Construction du contexte Jinja
    raw_nb_avis = lead.get('nb_avis') or lead.get('reviews_count')
    nb_avis     = str(int(raw_nb_avis)) if raw_nb_avis not in (None, '', 0) else '--'
    raw_rating  = lead.get('rating') or lead.get('note')
    rating      = f"{float(raw_rating):.1f}" if raw_rating not in (None, '') else '--'
    logo_url    = lead.get('logo_url') or ''

    context = {
        'NOM_ENTREPRISE':     nom,
        'NOM_ENTREPRISE_COURT': nom_court,
        'VILLE':              lead.get('ville') or 'Votre Ville',
        'TELEPHONE':          lead.get('telephone') or 'Nous contacter',
        'ADRESSE':            lead.get('adresse') or '',
        'NB_AVIS':            nb_avis,
        'RATING':             rating,
        'ANNEE_CREATION':     '2018',
        'LOGO_URL':           logo_url,
        'screenshot_desktop': None,
        'screenshot_mobile':  None,
        # Defaults sectoriels
        'SECTEUR_TAGLINE':      sector_defs.get('SECTEUR_TAGLINE', 'Commerce Local'),
        'NB_CHAMBRES':          sector_defs.get('NB_CHAMBRES', '--'),
        'SPECIALITE':           sector_defs.get('SPECIALITE', 'Expert local'),
        'SPECIALITE_MEDICALE':  sector_defs.get('SPECIALITE_MEDICALE', 'Généraliste'),
        'TYPE_COMMERCE':        sector_defs.get('TYPE_COMMERCE', 'Commerce'),
        'TYPE_AGENCE':          sector_defs.get('TYPE_AGENCE', 'Agence'),
        'TYPE_BIJOUTERIE':      sector_defs.get('TYPE_BIJOUTERIE', 'Joaillerie'),
    }

    # Rendu Jinja2
    jinja_env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_path.parent)),
        autoescape=False,
        undefined=jinja2.Undefined,  # variables manquantes → vide silencieux
    )
    template = jinja_env.from_string(template_text)
    html = template.render(context)

    # Nettoyer les variables non résolues restantes (sécurité)
    html = re.sub(r'\{\{[A-Za-z0-9_|" \-\.]+\}\}', '--', html)

    # URL-encoder le nom d'entreprise dans les URLs WhatsApp
    import urllib.parse
    html = re.sub(
        r'href="(https://wa\.me/\d+\?text=[^"]*?)site%20de%20([^"]+)"',
        lambda m: f'href="{m.group(1)}site%20de%20{urllib.parse.quote(m.group(2), safe="")}"',
        html,
    )

    # Remplacer les ratings statiques 4.8 par la note réelle
    html = replace_static_rating(html, rating)

    # Ne pas afficher la section mockup. Le logo reste visible si disponible.
    html = remove_logo_and_mockup(html, logo_url=logo_url)

    # Logo désactivé : on affiche toujours uniquement le nom texte
    # (force_logo_display est un no-op)

    # Sauvegarde
    safe_name = re.sub(r'[^\w\-]', '_', nom_court)[:50]
    output_path = RAPPORTS_DIR / f'rapport_{lead_id}_{safe_name}.html'
    # S'assurer que le HTML est responsive pour les aperçus / captures
    html = ensure_responsive(html)
    html = html.replace(
        '</head>',
        '<script defer data-domain="audit.incidenx.com" src="https://plausible.io/js/script.js"></script>\n</head>'
    )
    output_path.write_text(html, encoding='utf-8')

    return html, output_path


# Labels lisibles pour les secteurs (pour le message WhatsApp)
SECTOR_LABELS = {
    'hotellerie':  'hôtellerie & restauration',
    'restaurant':  'restauration',
    'beaute':      'beauté & bien-être',
    'sante':       'santé & médical',
    'juridique':   'services juridiques',
    'immobilier':  'immobilier',
    'artisan':     'artisanat',
    'auto':        'automobile',
    'bijouterie':  'bijouterie & joaillerie',
    'commerce':    'commerce local',
    'sport':       'sport & coaching',
    'comptable':   'expertise comptable',
    'education':   'éducation & formation',
    'evenementiel':'événementiel & réception',
    'microfinance':'microfinance & services financiers',
    'ong':         'ong & association',
    'default':     'commerce local',
}


def build_whatsapp_message(lead: dict) -> str:
    """Génère le message WhatsApp prêt à copier-coller."""
    nom      = lead.get('nom') or 'vous'
    prenom   = lead.get('prenom_gerant') or ''
    ville    = (lead.get('ville') or 'votre ville').title()

    # Secteur lisible
    sector_folder = resolve_sector(lead.get('secteur'), lead.get('category'))
    secteur_label = SECTOR_LABELS.get(sector_folder, 'votre secteur')

    salutation = f"Bonjour {prenom}," if prenom else "Bonjour,"

    msg = f"""{salutation}

Je m'appelle Jean-Marc, je suis consultant web local basé à Paris.

En analysant les professionnels de {secteur_label} à {ville}, j'ai remarqué que *{nom}* n'avait pas encore de site web — et c'est une vraie opportunité à saisir avant vos concurrents.

J'ai préparé une maquette personnalisée pour vous montrer à quoi pourrait ressembler votre présence en ligne. C'est gratuit, sans engagement.

Vous avez 2 minutes pour y jeter un œil ?

— Jean-Marc · Incidenx
📞 06 12 34 56 78
🌐 incidenx.com"""

    return msg


def generate_report_no_site(lead_id: int, open_browser: bool = False) -> dict:
    """
    Pipeline complète pour un lead sans site.

    Returns:
        {
          'lead':             dict du lead,
          'sector_folder':    str,
          'template_used':    str (nom du fichier),
          'html_path':        Path,
          'whatsapp_message': str,
        }
    """
    lead = load_lead(lead_id)

    # Vérification : le lead n'a vraiment pas de site
    site = lead.get('site_web') or ''
    if site and site not in ('SANS SITE', 'sans_site'):
        print(f"[ATTENTION] Le lead {lead_id} a un site : {site}")
        print("  On génère quand même le rapport Profil A.")

    html, output_path = render_html(lead)

    sector_folder = resolve_sector(lead.get('secteur'), lead.get('category'))
    template_path = pick_template(sector_folder, lead_id)

    whatsapp = build_whatsapp_message(lead)

    result = {
        'lead':             lead,
        'sector_folder':    sector_folder,
        'template_used':    template_path.name,
        'html_path':        output_path,
        'whatsapp_message': whatsapp,
    }

    if open_browser:
        webbrowser.open(output_path.as_uri())

    return result


# ── CLI ────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Génère un rapport Profil A pour un lead sans site.')
    parser.add_argument('--lead-id', type=int, help='ID du lead dans leads_bruts')
    parser.add_argument('--open', action='store_true', help='Ouvre le rapport dans le navigateur')
    parser.add_argument('--list', action='store_true', help='Liste les 10 premiers leads sans site')
    args = parser.parse_args()

    if args.list:
        leads = load_lead_no_site(limit=10)
        if not leads:
            print("Aucun lead sans site trouvé.")
        else:
            print(f"\n{'ID':>5}  {'Nom':<40}  {'Secteur':<20}  {'Ville':<20}  {'Logo'}")
            print('-' * 100)
            for l in leads:
                logo = 'OUI' if l.get('logo_url') else 'NON'
                print(f"{l['id']:>5}  {(l['nom'] or ''):<40}  {(l.get('secteur') or l.get('category') or ''):<20}  {(l.get('ville') or ''):<20}  {logo}")
        raise SystemExit(0)

    if not args.lead_id:
        # Prendre le premier lead sans site disponible
        leads = load_lead_no_site(limit=1)
        if not leads:
            print("[ERREUR] Aucun lead sans site trouvé dans la base.")
            raise SystemExit(1)
        lead_id = leads[0]['id']
        print(f"[INFO] Aucun --lead-id fourni. Utilisation du premier lead sans site : id={lead_id}")
    else:
        lead_id = args.lead_id

    result = generate_report_no_site(lead_id, open_browser=args.open)

    print("\n" + "=" * 60)
    print("  RAPPORT PROFIL A GÉNÉRÉ")
    print("=" * 60)
    print(f"  Lead ID      : {result['lead']['id']}")
    print(f"  Nom          : {result['lead']['nom']}")
    print(f"  Secteur DB   : {result['lead'].get('secteur') or result['lead'].get('category')}")
    print(f"  Secteur résolu: {result['sector_folder']}")
    print(f"  Template     : {result['template_used']}")
    print(f"  Logo URL     : {result['lead'].get('logo_url') or '(aucun)'}")
    print(f"  Fichier HTML : {result['html_path']}")
    print("\n" + "─" * 60)
    print("  MESSAGE WHATSAPP (copier-coller) :")
    print("─" * 60)
    print(result['whatsapp_message'])
    print("=" * 60)
