import os
import re
import logging
from pathlib import Path
from playwright.sync_api import sync_playwright

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

    # Juridique / Conseil financier
    if any(k in cat for k in ["avocat", "juridique", "notaire", "huissier",
                               "expert-comptable", "comptable", "commissaire",
                               "conseiller financier", "cabinet conseil",
                               "patrimoine", "fiscaliste", "auditeur"]):
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

        html = template_path.read_text(encoding="utf-8")

        # 3. Personnalisation des variables
        nom_complet = lead.get("nom", "Votre Entreprise")
        nom_affiche = (nom_complet[:37] + '...') if len(nom_complet) > 40 else nom_complet
        nb_avis = str(lead.get("nb_avis") or lead.get("reviews_count") or 0)

        replacements = {
            "{{NOM_ENTREPRISE}}":       nom_affiche,
            "{{VILLE}}":                lead.get("ville", "Votre Ville"),
            "{{TELEPHONE}}":            lead.get("telephone", "Contactez-nous"),
            "{{ADRESSE}}":              lead.get("adresse", ""),
            "{{NB_AVIS}}":              nb_avis,
            "{{ANNEE_CREATION}}":       "2018",
            "{{LOGO_URL}}":             lead.get("logo_url", ""),
            "{{SECTEUR_TAGLINE}}":      config.get("tagline", "Professionnel Local"),
            # Fallbacks sectoriels
            "{{NB_CHAMBRES}}":          "--",
            "{{SPECIALITE}}":           "Expertise Locale",
            "{{SPECIALITE_MEDICALE}}":  "Généraliste",
            "{{TYPE_COMMERCE}}":        "Boutique",
            "{{TYPE_AGENCE}}":          "Agence Immobilière",
            "{{TYPE_BIJOUTERIE}}":      "Joaillerie",
        }

        for key, val in replacements.items():
            html = html.replace(key, str(val))

        # 4. Nettoyage des tags non remplacés
        html = re.sub(r'\{\{[A-Z0-9_]+\}\}', '--', html)

        # 5. Remplacement couleur d'accent (si nécessaire)
        base_color = _TEMPLATE_BASE_COLORS.get(template_filename)
        target_color = config.get("color")
        if base_color and target_color and base_color != target_color:
            html = html.replace(base_color, target_color)

        # 6. Injection du logo
        if lead.get("logo_url"):
            html = html.replace("display:none; /* Python met display:block si logo dispo */", "display:block;")
            html = html.replace("display:block; /* Nom texte — affiché par défaut */", "display:none;")

        # 7. Sauvegarde temporaire pour Playwright
        nom_raw = lead.get("nom", "p")
        nom_slug = re.sub(r'[^a-zA-Z0-9\s-]', '', nom_raw.lower())
        nom_slug = re.sub(r'\s+', '-', nom_slug.strip())[:50]

        if lead.get("id"):
            html_path = current_dir / f"tmp_lead_{lead['id']}.html"
        else:
            html_path = current_dir / f"tmp_{nom_slug}.html"
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

        # 9. Capture Playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"file:///{html_path.absolute()}")
            page.wait_for_timeout(1000)

            page.set_viewport_size({"width": 1280, "height": 800})
            page.screenshot(path=str(desktop_path), full_page=False)

            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_timeout(500)
            page.screenshot(path=str(mobile_path), full_page=False)

            browser.close()

        # 10. Nettoyage
        if html_path.exists():
            html_path.unlink()

        logger.info(f"✅ Mockup généré : {nom_slug} | Template : {template_filename} | Secteur : {sector_key}")

        return {
            "success": True,
            "screenshot_desktop": str(desktop_path),
            "screenshot_mobile":  str(mobile_path),
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
            "template_used":      "",
            "secteur":            "",
            "erreur":             str(e),
        }
