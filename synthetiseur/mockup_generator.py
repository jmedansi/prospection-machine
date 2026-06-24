import os
import re
import sys
import logging
from pathlib import Path

import jinja2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.browser import cdp_tab

logger = logging.getLogger(__name__)

SECTOR_CONFIG = {
    "restaurant": {
        "templates": ["restaurant-hero-1-moderne.html", "restaurant-hero-2-chaleureux.html"],
        "color": "#c8a96e",
        "tagline": "Restaurant & Gastronomie",
    },
    "hotellerie": {
        "templates": ["hotellerie-hero-1-luxe.html", "hotellerie-hero-2-urbain.html"],
        "color": "#b5924c",
        "tagline": "Hôtellerie & Hébergement",
    },
    "sante": {
        "templates": ["sante-hero-1-confiance.html", "sante-hero-2-lumineux.html"],
        "color": "#0077b6",
        "tagline": "Santé & Bien-être",
    },
    "juridique": {
        "templates": ["juridique-hero-1-institutionnel.html", "juridique-hero-2-moderne.html"],
        "color": "#1e3a5f",
        "tagline": "Conseil Juridique & Expertise",
    },
    "beaute": {
        "templates": ["beaute-hero-1-elegant.html", "beaute-hero-2-moderne.html"],
        "color": "#c9a0a0",
        "tagline": "Beauté & Soins",
    },
    "commerce": {
        "templates": ["commerce-hero-1-boutique.html", "commerce-hero-2-artisan.html"],
        "color": "#e76f51",
        "tagline": "Commerce Local",
    },
    "immobilier": {
        "templates": ["immobilier-hero-1-premium.html", "immobilier-hero-2-moderne.html"],
        "color": "#1a3c34",
        "tagline": "Immobilier",
    },
    "bijouterie": {
        "templates": ["bijouterie-hero-1-luxe.html", "bijouterie-hero-2-tendance.html"],
        "color": "#d4af37",
        "tagline": "Joaillerie & Bijouterie",
    },
    "artisan": {
        "templates": ["artisan-hero-1-robuste.html", "artisan-hero-2-expertise.html"],
        "color": "#e07b39",
        "tagline": "Artisan de Confiance",
    },
    "sport": {
        "templates": ["sport-hero-1-energie.html", "sport-hero-2-coach.html"],
        "color": "#00c896",
        "tagline": "Sport & Remise en Forme",
    },
    "auto": {
        "templates": ["auto-hero-1-technique.html", "auto-hero-2-moderne.html"],
        "color": "#e63946",
        "tagline": "Automobile & Transport",
    },
    "numerique": {
        "templates": ["numerique-hero-1-tech.html", "numerique-hero-2-creatif.html"],
        "color": "#7c3aed",
        "tagline": "Expertise Digitale",
    },
    "comptable": {
        "templates": ["comptable-hero-1-institutionnel.html", "comptable-hero-2-moderne.html"],
        "color": "#1a5276",
        "tagline": "Expertise Comptable & Gestion",
    },
    "education": {
        "templates": ["education-hero-1-savoir.html", "education-hero-2-avenir.html"],
        "color": "#c0392b",
        "tagline": "Éducation & Formation",
    },
    "evenementiel": {
        "templates": ["evenementiel-hero-1-prestige.html", "evenementiel-hero-2-creatif.html"],
        "color": "#d4af37",
        "tagline": "Événementiel & Réception",
    },
    "microfinance": {
        "templates": ["microfinance-hero-1-confiance.html", "microfinance-hero-2-moderne.html"],
        "color": "#1a5276",
        "tagline": "Microfinance & Services Financiers",
    },
    "default": {
        "templates": ["default-hero-1-professionnel.html", "default-hero-2-chaleureux.html"],
        "color": "#3d5a80",
        "tagline": "Professionnel Local",
    },
}

# Couleur de base de chaque template (celle que Python remplace)
_TEMPLATE_BASE_COLORS = {
    "restaurant-hero-1-moderne.html":      "#c8a96e",
    "restaurant-hero-2-chaleureux.html":   "#d4822a",
    "hotellerie-hero-1-luxe.html":         "#b5924c",
    "hotellerie-hero-2-urbain.html":       "#e9c46a",
    "sante-hero-1-confiance.html":         "#0077b6",
    "sante-hero-2-lumineux.html":          "#00b4d8",
    "juridique-hero-1-institutionnel.html":"#1e3a5f",
    "juridique-hero-2-moderne.html":       "#2d6a4f",
    "beaute-hero-1-elegant.html":          "#c9a0a0",
    "beaute-hero-2-moderne.html":          "#f4a261",
    "commerce-hero-1-boutique.html":       "#e76f51",
    "commerce-hero-2-artisan.html":        "#2a9d8f",
    "immobilier-hero-1-premium.html":      "#1a3c34",
    "immobilier-hero-2-moderne.html":      "#e07a5f",
    "bijouterie-hero-1-luxe.html":         "#d4af37",
    "bijouterie-hero-2-tendance.html":     "#c77dff",
    "artisan-hero-1-robuste.html":         "#e07b39",
    "artisan-hero-2-expertise.html":       "#4a7c59",
    "sport-hero-1-energie.html":           "#00c896",
    "sport-hero-2-coach.html":             "#e63946",
    "auto-hero-1-technique.html":          "#e63946",
    "auto-hero-2-moderne.html":            "#1a73e8",
    "numerique-hero-1-tech.html":          "#7c3aed",
    "numerique-hero-2-creatif.html":       "#0d9488",
    "comptable-hero-1-institutionnel.html":"#1a5276",
    "comptable-hero-2-moderne.html":       "#1a5276",
    "education-hero-1-savoir.html":        "#c0392b",
    "education-hero-2-avenir.html":        "#06b6d4",
    "evenementiel-hero-1-prestige.html":   "#d4af37",
    "evenementiel-hero-2-creatif.html":    "#8b5cf6",
    "microfinance-hero-1-confiance.html":  "#1a5276",
    "microfinance-hero-2-moderne.html":    "#0891b2",
    "default-hero-1-professionnel.html":   "#3d5a80",
    "default-hero-2-chaleureux.html":      "#457b9d",
}


def detect_sector(category: str) -> str:
    """Détecte le secteur depuis la catégorie GMB ou le secteur saisi."""
    cat = str(category).lower()

    # Restaurant / Alimentation
    if any(k in cat for k in ["restaurant", "café", "cafe", "boulangerie", "pizzeria",
                               "brasserie", "bistrot", "traiteur", "sandwicherie",
                               "sushi", "kebab", "fast food", "snack", "épicerie fine",
                               "cave à vins", "wine", "bar "]):
        return "restaurant"

    # Hôtellerie
    if any(k in cat for k in ["hôtel", "hotel", "auberge", "camping", "chambre",
                               "gîte", "bed and breakfast", "résidence", "lodge"]):
        return "hotellerie"

    # Santé / Médical
    if any(k in cat for k in ["médecin", "medecin", "clinique", "dentiste", "santé",
                               "medical", "kiné", "kinésithérapeute", "ostéopathe",
                               "osteopathe", "naturopathe", "psychologue", "psychiatre",
                               "pharmacie", "infirmier", "podologue", "orthophoniste",
                               "ophtalmologue", "cardiologue", "dermatologue",
                               "nutritionniste", "diététicien", "sage-femme"]):
        return "sante"

    # Comptable / Expertise comptable
    if any(k in cat for k in ["expert-comptable", "expertise comptable",
                               "comptable", "cabinet comptable", "fiscal"]):
        return "comptable"

    # Juridique / Conseil financier
    if any(k in cat for k in ["avocat", "juridique", "notaire", "huissier",
                               "commissaire", "conseiller financier",
                               "cabinet conseil", "patrimoine", "fiscaliste",
                               "auditeur"]):
        return "juridique"

    # Immobilier
    if any(k in cat for k in ["immobilier", "agence immobilière", "propriété",
                               "estate", "promoteur", "syndic", "foncier",
                               "location saisonnière"]):
        return "immobilier"

    # Beauté / Coiffure / Bien-être
    if any(k in cat for k in ["salon", "coiffeur", "coiffure", "beauté", "spa",
                               "esthétique", "esthetique", "onglerie", "barbier",
                               "massage", "bien-être", "bien être", "nail",
                               "institut de beauté", "maquillage", "épilation"]):
        return "beaute"

    # Bijouterie
    if any(k in cat for k in ["bijouterie", "bijoux", "joaillerie", "horlogerie",
                               "montre", "diamant", "orfèvre"]):
        return "bijouterie"

    # Artisans / BTP
    if any(k in cat for k in ["plombier", "plomberie", "électricien", "electricien",
                               "menuisier", "menuiserie", "peintre", "peinture",
                               "maçon", "maconnerie", "couvreur", "toiture",
                               "carreleur", "carrelage", "chauffagiste", "chauffage",
                               "serrurier", "serrurerie", "architecte", "paysagiste",
                               "jardinier", "jardinage", "climatisation", "clim",
                               "btp", "bâtiment", "batiment", "travaux", "renovation",
                               "rénovation", "isolation", "vitrier", "vitrerie",
                               "déménageur", "demenageur", "charpentier"]):
        return "artisan"

    # Sport / Fitness / Bien-être physique
    if any(k in cat for k in ["salle de sport", "fitness", "gym", "coach sportif",
                               "personal trainer", "yoga", "pilates", "danse",
                               "natation", "tennis", "foot", "football", "rugby",
                               "crossfit", "musculation", "sport", "piscine",
                               "école de danse", "arts martiaux", "judo", "karaté"]):
        return "sport"

    # Éducation / Formation
    if any(k in cat for k in ["école", "ecole", "formation", "éducation", "education",
                               "lycée", "lycee", "collège", "college", "université",
                               "universite", "cours", "apprentissage", "institut de formation",
                               "centre de formation", "auto-école", "auto école"]):
        return "education"

    # Événementiel / Réception
    if any(k in cat for k in ["événementiel", "evenementiel", "wedding", "mariage",
                               "organisation", "salle de réception", "salle de reception",
                               "décoration", "decoration", "traiteur", "réception",
                               "reception", "wedding planner", "fête", "fete",
                               "cérémonie", "ceremonie", "prestataire mariage"]):
        return "evenementiel"

    # Microfinance / Services financiers
    if any(k in cat for k in ["microfinance", "microcrédit", "microcredit",
                               "institution de microfinance", "imf", "micro finance"]):
        return "microfinance"

    # Automobile / Transport
    if any(k in cat for k in ["garage", "garagiste", "carrosserie", "carrossier",
                               "auto-école", "auto école", "automobile", "mécanic",
                               "mecanique", "taxi", "vtc", "transport", "location voiture",
                               "pneu", "pneumatique", "contrôle technique"]):
        return "auto"

    # Numérique / Créatif
    if any(k in cat for k in ["photographe", "photographie", "vidéaste", "videaste",
                               "graphiste", "web designer", "webdesigner",
                               "développeur", "developpeur", "consultant digital",
                               "agence web", "agence communication", "communication",
                               "marketing", "seo", "réseaux sociaux", "social media",
                               "créatif", "creatif", "studio", "agence créative"]):
        return "numerique"

    # Commerce local (fallback après tous les spécifiques)
    if any(k in cat for k in ["magasin", "boutique", "commerce", "épicerie",
                               "librairie", "fleuriste", "opticien", "pharmacie",
                               "pressing", "laverie", "cordonnerie"]):
        return "commerce"

    return "default"


def format_rating(value):
    try:
        if value is None or value == "":
            return None
        return f"{float(value):.1f}"
    except Exception:
        return None


def force_logo_display(html: str) -> str:
    # Logo image désactivé : on affiche uniquement le nom texte
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
        (r'(?<![0-9A-Za-z])4\.8(?![0-9A-Za-z])', f'{rating}'),
        (r'>\s*4\.8\s*<', f'>{rating}<'),
    ]

    for pattern, replacement in replacements:
        html = re.sub(pattern, replacement, html)

    return html


def generate_mockup(lead: dict) -> dict:
    """
    Génère 2 screenshots (desktop + mobile) du hero personnalisé.
    """
    try:
        # 1. Détecter le secteur (priorité : secteur saisi > catégorie GMB)
        sector_key = detect_sector(lead.get("secteur") or lead.get("category", ""))
        config = SECTOR_CONFIG.get(sector_key, SECTOR_CONFIG["default"])

        # 2. Choisir le template
        lead_id = lead.get("id", 0)
        template_idx = lead_id % len(config["templates"])
        template_filename = config["templates"][template_idx]

        current_dir = Path(__file__).parent.absolute()
        template_path = current_dir / "templates_sites" / sector_key / template_filename

        if not template_path.exists():
            logger.warning(f"Template {template_filename} introuvable pour {sector_key}, bascule sur default.")
            sector_key = "default"
            config = SECTOR_CONFIG[sector_key]
            template_idx = lead_id % len(config["templates"])
            template_filename = config["templates"][template_idx]
            template_path = current_dir / "templates_sites" / "default" / template_filename

        template_text = template_path.read_text(encoding="utf-8")

        # 3. Personnalisation des variables
        nom_complet = lead.get("nom", "Votre Entreprise")
        nom_affiche = (nom_complet[:37] + '...') if len(nom_complet) > 40 else nom_complet
        nb_avis = str(lead.get("nb_avis") or lead.get("reviews_count") or 0)
        rating = format_rating(lead.get("rating") or lead.get("note") or 0) or "0.0"

        jinja_context = {
            "NOM_ENTREPRISE":      nom_affiche,
            "VILLE":               lead.get("ville", "Votre Ville"),
            "TELEPHONE":           lead.get("telephone", "Contactez-nous"),
            "ADRESSE":             lead.get("adresse", ""),
            "NB_AVIS":             nb_avis,
            "RATING":              rating,
            "ANNEE_CREATION":      "2018",
            "LOGO_URL":            lead.get("logo_url") or "",
            "SECTEUR_TAGLINE":     config.get("tagline", "Professionnel Local"),
            "NB_CHAMBRES":         "--",
            "SPECIALITE":          "Expertise Locale",
            "SPECIALITE_MEDICALE": "Généraliste",
            "TYPE_COMMERCE":       "Boutique",
            "TYPE_AGENCE":         "Agence Immobilière",
            "TYPE_BIJOUTERIE":     "Joaillerie",
            "screenshot_desktop":  None,
            "screenshot_mobile":   None,
        }

        jinja_loader = jinja2.FileSystemLoader(str(current_dir / "templates_sites" / sector_key))
        jinja_env = jinja2.Environment(loader=jinja_loader, autoescape=False)
        template = jinja_env.from_string(template_text)
        html = template.render(jinja_context)
        html = replace_static_rating(html, rating)

        # 4. Nettoyage des tags non remplacés (s'il en reste)
        html = re.sub(r'\{\{[A-Za-z0-9_]+\}\}', '--', html)

        # 5. URL-encoder le nom d'entreprise dans les URLs WhatsApp
        import urllib.parse
        html = re.sub(
            r'href="(https://wa\.me/\d+\?text=[^"]*?)site%20de%20([^"]+)"',
            lambda m: f'href="{m.group(1)}site%20de%20{urllib.parse.quote(m.group(2), safe="")}"',
            html,
        )

        # 6. Remplacement couleur d'accent (si nécessaire)
        base_color = _TEMPLATE_BASE_COLORS.get(template_filename)
        target_color = config.get("color")
        if base_color and target_color and base_color != target_color:
            html = html.replace(base_color, target_color)

        # 7. Sauvegarde temporaire pour Playwright
        nom_raw = lead.get("nom", "p")
        nom_slug = re.sub(r'[^a-zA-Z0-9\s]', '', nom_raw.lower())
        nom_slug = re.sub(r'\s+', '-', nom_slug.strip()).strip('-')[:50]

        if lead.get("id"):
            html_path = current_dir / f"tmp_lead_{lead['id']}.html"
        else:
            html_path = current_dir / f"tmp_{nom_slug}.html"
        # Rendre responsive avant d'écrire
        html = ensure_responsive(html)
        html = html.replace(
            '</head>',
            '<script defer data-domain="audit.incidenx.com" src="https://plausible.io/js/script.js"></script>\n</head>'
        )
        html_path.write_text(html, encoding="utf-8")

        # 8. Dossier de sortie
        output_dir = Path("mockups/screenshots")
        output_dir.mkdir(parents=True, exist_ok=True)
        if lead.get("id"):
            desktop_path = output_dir / f"lead_{lead['id']}_desktop.png"
            mobile_path  = output_dir / f"lead_{lead['id']}_mobile.png"
        else:
            desktop_path = output_dir / f"{nom_slug}_desktop.png"
            mobile_path  = output_dir / f"{nom_slug}_mobile.png"

        # 9. Capture via Chrome Gemini (CDP)
        with cdp_tab(viewport={"width": 1280, "height": 800}) as page:
            page.goto(f"file:///{html_path.absolute()}")
            page.wait_for_timeout(1000)

            page.screenshot(path=str(desktop_path), full_page=False)

            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_timeout(500)
            page.screenshot(path=str(mobile_path), full_page=False)

        # 10. Copier le HTML + screenshots dans reporter/reports/{slug}/
        import shutil
        rapport_dir = Path("reporter/reports") / nom_slug
        rapport_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(html_path, rapport_dir / "index.html")
        if desktop_path.exists():
            shutil.copy2(desktop_path, rapport_dir / desktop_path.name)
        if mobile_path.exists():
            shutil.copy2(mobile_path, rapport_dir / mobile_path.name)

        # 11. Nettoyage du fichier temporaire
        if html_path.exists():
            html_path.unlink()

        rapport_local = str(rapport_dir)
        logger.info(f"✅ Mockup généré : {nom_slug} | Template : {template_filename} | Secteur : {sector_key}")
        logger.info(f"   Rapport local : {rapport_local}")

        return {
            "success": True,
            "screenshot_desktop": str(desktop_path),
            "screenshot_mobile":  str(mobile_path),
            "rapport_local":      rapport_local,
            "rapport_slug":       nom_slug,
            "template_used":      template_filename,
            "secteur":            sector_key,
            "erreur":             None,
        }

    except Exception as e:
        logger.error(f"❌ Erreur génération mockup : {e}")
        return {
            "success":            False,
            "screenshot_desktop": "",
            "screenshot_mobile":  "",
            "rapport_local":      "",
            "rapport_slug":       "",
            "template_used":      "",
            "secteur":            "",
            "erreur":             str(e),
        }
