import os
import logging
from pathlib import Path
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

SECTOR_CONFIG = {
    "restaurant": {
        "templates": ["restaurant-hero-1-moderne.html", "restaurant-hero-2-chaleureux.html"],
        "color": "#c8a96e"
    },
    "hotellerie": {
        "templates": ["hotellerie-hero-1-luxe.html", "hotellerie-hero-2-urbain.html"],
        "color": "#d4af37"
    },
    "sante": {
        "templates": ["sante-hero-1-confiance.html", "sante-hero-2-lumineux.html"],
        "color": "#0077b6"
    },
    "juridique": {
        "templates": ["juridique-hero-1-institutionnel.html", "juridique-hero-2-moderne.html"],
        "color": "#1e3a5f"
    },
    "beaute": {
        "templates": ["beaute-hero-1-elegant.html", "beaute-hero-2-moderne.html"],
        "color": "#f4a261"
    },
    "commerce": {
        "templates": ["commerce-hero-1-boutique.html", "commerce-hero-2-artisan.html"],
        "color": "#e67e22"
    },
    "immobilier": {
        "templates": ["immobilier-hero-1-premium.html", "immobilier-hero-2-moderne.html"],
        "color": "#2c3e50"
    },
    "bijouterie": {
        "templates": ["bijouterie-hero-1-luxe.html", "bijouterie-hero-2-tendance.html"],
        "color": "#d4af37"
    },
    "default": {
        "templates": ["default-hero-1-professionnel.html", "default-hero-2-chaleureux.html"],
        "color": "#1a73e8"
    }
}


def detect_sector(category: str) -> str:
    """Détecte grossièrement le secteur depuis la catégorie GMB."""
    cat = str(category).lower()
    if any(k in cat for k in ["restaurant", "café", "boulangerie", "pizzeria"]):
        return "restaurant"
    if any(k in cat for k in ["avocat", "juridique", "notaire", "huissier"]):
        return "juridique"
    if any(k in cat for k in ["médecin", "clinique", "dentiste", "santé", "medical"]):
        return "sante"
    if any(k in cat for k in ["hôtel", "auberge", "camping", "chambre"]):
        return "hotellerie"
    if any(k in cat for k in ["immobilier", "agence", "propriété", "estate"]):
        return "immobilier"
    if any(k in cat for k in ["salon", "coiffeur", "coiffure", "beauté", "spa", "esthétique", "onglerie", "barbier"]):
        return "beaute"
    if any(k in cat for k in ["bijouterie", "bijoux", "joaillerie", "horlogerie", "montre", "diamant"]):
        return "bijouterie"
    if any(k in cat for k in ["magasin", "boutique", "commerce", "épicerie"]):
        return "commerce"
    return "default"


def generate_mockup(lead: dict) -> dict:
    """
    Génère 2 screenshots (desktop + mobile) du hero personnalisé.
    """
    try:
        # 1. Détecter le secteur
        sector_key = detect_sector(lead.get("category", ""))
        config = SECTOR_CONFIG.get(sector_key, SECTOR_CONFIG["default"])
        # 2. Choisir le template dans la liste configurée
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

        replacements = {
            "{{NOM_ENTREPRISE}}": nom_affiche,
            "{{VILLE}}": lead.get("ville", "Votre Ville"),
            "{{TELEPHONE}}": lead.get("telephone", "Contactez-nous"),
            "{{ADRESSE}}": lead.get("adresse", ""),
            "{{NB_AVIS}}": str(lead.get("reviews_count", 0)),
            "{{ANNEE_CREATION}}": "2018", # Valeur par défaut
            "{{LOGO_URL}}": lead.get("logo_url", ""),
            # Fallbacks sectoriels pour éviter les tags visibles
            "{{NB_CHAMBRES}}": "--",
            "{{SPECIALITE}}": "Expertise Locale",
            "{{SPECIALITE_MEDICALE}}": "Généraliste",
            "{{TYPE_COMMERCE}}": "Boutique",
            "{{TYPE_AGENCE}}": "Agence Immobilière",
            "{{TYPE_BIJOUTERIE}}": "Joaillerie",
        }

        for key, val in replacements.items():
            html = html.replace(key, str(val))

        # Nettoyage final : remplacer tout tag {{TAG}} restant par un placeholder propre (ex: --)
        import re
        html = re.sub(r'\{\{[A-Z0-9_]+\}\}', '--', html)

        # 4. Remplacement de la couleur d'accent (si spécifiée dans le template)
        # Chaque secteur a une couleur de base dans son template qu'on peut surcharger
        sector_base_color = config.get("color", "#1a73e8")
        # On pourrait ici utiliser une couleur spécifique venant de l'audit si on voulait
        # html = html.replace("#c8a96e", sector_base_color) # Ex pour restaurant

        # 5. Injection du logo (logique CSS)
        if lead.get("logo_url"):
            html = html.replace("display:none; /* Python met display:block si logo dispo */", "display:block;")
            html = html.replace("display:block; /* Nom texte — affiché par défaut */", "display:none;")

        # 6. Sauvegarde temporaire pour Playwright
        # Nettoyer le nom pour créer un slug valide (sans |, &, é, etc.)
        import re
        nom_raw = lead.get("nom", "p")
        # Garder uniquement lettres, chiffres, espaces et tirets
        nom_slug = re.sub(r'[^a-zA-Z0-9\s-]', '', nom_raw.lower())
        nom_slug = re.sub(r'\s+', '-', nom_slug.strip())[:50]  # Max 50 chars
        
        # Utiliser l'ID si disponible pour garantir l'unicité
        if lead.get("id"):
            html_path = current_dir / f"tmp_lead_{lead['id']}.html"
        else:
            html_path = current_dir / f"tmp_{nom_slug}.html"
        html_path.write_text(html, encoding="utf-8")

        # 7. Dossier de sortie
        output_dir = Path("mockups/screenshots")
        output_dir.mkdir(parents=True, exist_ok=True)
        if lead.get("id"):
            desktop_path = output_dir / f"lead_{lead['id']}_desktop.png"
            mobile_path = output_dir / f"lead_{lead['id']}_mobile.png"
        else:
            desktop_path = output_dir / f"{nom_slug}_desktop.png"
            mobile_path = output_dir / f"{nom_slug}_mobile.png"

        # 8. Capture Playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"file:///{html_path.absolute()}")
            page.wait_for_timeout(1000) # Laisser le temps pour les animations

            page.set_viewport_size({"width": 1280, "height": 800})
            page.screenshot(path=str(desktop_path), full_page=False)

            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_timeout(500)
            page.screenshot(path=str(mobile_path), full_page=False)

            browser.close()

        # 9. Nettoyage
        if html_path.exists():
            html_path.unlink()

        logger.info(f"✅ Mockup généré : {nom_slug} | Template : {template_filename} | Secteur : {sector_key}")

        return {
            "success": True,
            "screenshot_desktop": str(desktop_path),
            "screenshot_mobile": str(mobile_path),
            "template_used": template_filename,
            "secteur": sector_key,
            "erreur": None
        }

    except Exception as e:
        logger.error(f"❌ Erreur génération mockup : {e}")
        return {
            "success": False,
            "screenshot_desktop": "",
            "screenshot_mobile": "",
            "template_used": "",
            "secteur": "",
            "erreur": str(e)
        }
