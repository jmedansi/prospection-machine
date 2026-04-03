# -*- coding: utf-8 -*-
"""
copywriter/main.py
==================
Rôle UNIQUE : détecter la situation commerciale d'un lead (S1-S8)
et retourner le profil email correspondant pour email_builder.

CE MODULE NE GÉNÈRE PAS D'EMAILS HTML.
L'email HTML est généré exclusivement par envoi/email_builder.py
en utilisant les templates dans templates/emails/template_profil_{a,b,c,d}.html.

Mapping situation → profil email_builder (défini dans dashboard/pipeline.py) :
  S1 Site lent            → B
  S2 Pas de meta          → D
  S3 Peu d'avis           → C
  S4 Pas de site          → A
  S5 Note faible          → C
  S6 Pas de CTA           → B
  S7 Vieux CMS            → B
  S8 Bon GMB + site lent  → B
"""
import os
import sys
import logging
from typing import Dict, Any, List

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(current_dir, ".."))

# Configuration du logger
logging.basicConfig(
    filename='errors.log',
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- LOGIQUE D'IMPACT ---
def get_all_impacts(audit: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Évalue les 15 règles d'impact définies."""
    impacts = []
    rules = [
        ("mobile_score", lambda v: v < 50, 3),
        ("lcp_ms", lambda v: v > 4000, 3),
        ("has_https", lambda v: not v, 3),
        ("render_blocking_scripts", lambda v: (v or 0) > 2, 2),
        ("reviews_count", lambda v: (v or 0) < 10, 2),
        ("has_meta_description", lambda v: not v, 2),
        ("uses_cache", lambda v: not v, 2),
        ("tel_link", lambda v: not v, 2),
        ("photos_count", lambda v: (v or 0) < 5, 1),
        ("h1_count", lambda v: (v or 0) == 0, 1),
        ("has_contact_button", lambda v: not v, 1),
        ("images_without_alt", lambda v: (v or 0) > 3, 1),
        ("rating", lambda v: (v or 0.0) < 4.0, 1),
        ("cms_detected", lambda v: str(v).lower() in ["wix", "jimdo"], 1),
        ("has_analytics", lambda v: not v, 1),
    ]
    for critere, condition, impact_val in rules:
        valeur = audit.get(critere)
        if valeur is None:
            if critere in ["mobile_score", "rating"]: valeur = 100 if critere == "mobile_score" else 5.0
            elif critere in ["lcp_ms"]: valeur = 0
            elif critere in ["h1_count", "render_blocking_scripts", "photos_count", "reviews_count", "images_without_alt"]: valeur = 100 if critere != "render_blocking_scripts" else 0
            else: valeur = True if "has_" in critere or "_link" in critere or "uses_" in critere else False
        if condition(valeur):
            impacts.append({"critere": critere, "valeur": valeur, "impact": impact_val})
    return impacts

def extract_problemes_detectes(impacts: List[Dict[str, Any]], audit: Dict[str, Any]) -> List[str]:
    """Regroupe les anomalies techniques en catégories commerciales."""
    problemes = []
    site_status = audit.get("site_analysee")
    if site_status == "SANS SITE" or not audit.get("site_web"):
        problemes.append("pas de site")
    elif site_status == "ERREUR":
        problemes.append("pas de site")
    for imp in impacts:
        c = imp['critere']
        if c in ["mobile_score", "lcp_ms", "has_https", "render_blocking_scripts", "uses_cache", "tel_link"]:
            if "mauvais site" not in problemes: problemes.append("mauvais site")
        elif c in ["has_meta_description", "h1_count", "images_without_alt"]:
            if "mauvais seo" not in problemes: problemes.append("mauvais seo")
        elif c in ["rating", "reviews_count", "photos_count"]:
            if "mauvais GMB" not in problemes: problemes.append("mauvais GMB")
    return problemes

def determine_main_problem(problemes: List[str], impacts: List[Dict[str, Any]]) -> Dict[str, str]:
    """Sélectionne LE problème prioritaire selon la hiérarchie commerciale."""
    if "pas de site" in problemes:
        return {"service_propose": "Création Site Web", "probleme_principal": "pas de site web défini ou site inaccessible"}
    if "mauvais site" in problemes:
        web_criteres = ["mobile_score", "lcp_ms", "has_https", "render_blocking_scripts"]
        pire = next((i for i in impacts if i['critere'] in web_criteres), None)
        if pire and pire['critere'] == "lcp_ms":
            try:
                lcp_val = float(pire['valeur'])
                detail = f"Votre site charge en {lcp_val/1000:.1f}s sur mobile — 2x au-dessus de la référence hôtellerie"
            except:
                detail = "chargement très lent sur mobile"
        else:
            detail = f"{pire['critere']} = {pire['valeur']}" if pire else "chargement lent ou mauvaise optimisation"
        return {"service_propose": "Refonte Site Web / Optimisation technique", "probleme_principal": f"mauvais site ({detail})"}
    if "mauvais seo" in problemes:
        seo_criteres = ["has_meta_description", "h1_count", "images_without_alt"]
        pire = next((i for i in impacts if i['critere'] in seo_criteres), None)
        detail = "chargement rapide mais invisible sur Google"
        if pire:
            if pire['critere'] == "has_meta_description": detail = "aucune description Meta pour Google"
            elif pire['critere'] == "h1_count": detail = "structure H1 absente ou mauvaise"
            elif pire['critere'] == "images_without_alt": detail = "images non optimisées (alt manquant)"
        return {"service_propose": "Optimisation SEO", "probleme_principal": f"mauvais seo ({detail})"}
    if "mauvais GMB" in problemes:
        pire = next((i for i in impacts if i['critere'] in ["rating", "reviews_count", "photos_count"]), None)
        detail = f"{pire['critere']} = {pire['valeur']}" if pire else "manque de visibilité sur Maps"
        return {"service_propose": "Optimisation GMB", "probleme_principal": f"mauvais GMB ({detail})"}
    # --- 8 SITUATIONS → labels et arguments (PAS d'email ici) ---
# L'email HTML est généré par envoi/email_builder.py + templates/emails/
SITUATIONS_TEMPLATES = {
    "S1_LENT":           {"id": "S1", "label": "Site lent sur mobile",        "argument": "Votre site charge en {lcp_s}s sur mobile. 53% de vos visiteurs partent avant de voir vos services."},
    "S2_NO_META":        {"id": "S2", "label": "Pas de meta description",      "argument": "Votre meta description est absente. Google génère un extrait aléatoire — 2x moins de clics que vos concurrents."},
    "S3_LOW_REVIEWS":    {"id": "S3", "label": "Peu d'avis Google",            "argument": "Avec {reviews_count} avis, {nom} apparaît après des concurrents qui en ont 50+."},
    "S4_NO_SITE":        {"id": "S4", "label": "Pas de site web",              "argument": "Sans site web, {nom} est absent de 73% des recherches Google qui aboutissent à un contact."},
    "S5_LOW_RATING":     {"id": "S5", "label": "Note Google faible",           "argument": "Une note de {rating}/5 fait perdre en moyenne 35% des prospects qui vous trouvent sur Google."},
    "S6_NO_CTA":         {"id": "S6", "label": "Pas de bouton contact / tel",  "argument": "Votre site n'a pas de lien téléphonique cliquable sur mobile. 70% des visiteurs mobiles abandonnent."},
    "S7_OLD_CMS":        {"id": "S7", "label": "CMS vieillot (Wix/Jimdo)",     "argument": "Votre site utilise {cms_detected} — 2x plus lent que les sites modernes, pénalisé par Google."},
    "S8_GOOD_GMB_BAD_WEB":{"id": "S8","label": "Bon GMB, mauvais site",        "argument": "{nom} a {rating}/5 avec {reviews_count} avis. Mais le site charge en {lcp_s}s — vos avis attirent des prospects que votre site fait fuir."},
}

# --- PERSONA JEAN-MARC ---
SYSTEM_PROMPT = """
Tu es Jean-Marc, consultant en visibilité digitale pour les PME locales.
Style direct, sans jargon, pas commercial. 5 phrases max par mail. Signe : Jean-Marc.
"""

def generate_email_content(audit_dict: Dict[str, Any], main_problem: Dict[str, str]) -> Dict[str, Any]:
    """
    Détecte la situation commerciale et retourne :
      - phrase_synthese : label de la situation (ex: "Bon GMB, mauvais site")
      - diagnostic      : argument commercial personnalisé
      - rapport_resume  : idem
      - service_propose : type de service recommandé

    NE GÉNÈRE PAS d'email_objet ni d'email_corps.
    Ces champs sont produits par envoi/email_builder.py via les templates HTML.
    """
    m_score  = float(audit_dict.get('mobile_score') or 100)
    lcp_ms   = float(audit_dict.get('lcp_ms') or 0)
    rating   = float(audit_dict.get('rating') or 0)
    reviews  = int(audit_dict.get('reviews_count') or audit_dict.get('nb_avis') or 0)
    has_meta = bool(audit_dict.get('has_meta_description', True))
    has_site = bool(audit_dict.get('site_web'))
    has_cta  = bool(audit_dict.get('has_contact_button', True))
    tel_link = bool(audit_dict.get('tel_link', True))
    cms      = str(audit_dict.get('cms_detected') or "").lower()

    situation = None

    # Ordre de priorité des situations (seuils assouplis)
    if not has_site:
        situation = "S4_NO_SITE"
    elif rating >= 4.3 and reviews >= 30 and lcp_ms > 3000:
        # Bon GMB + site lent → contraste fort
        situation = "S8_GOOD_GMB_BAD_WEB"
    elif lcp_ms > 3000 or m_score < 65:
        # Site lent même si GMB moyen
        situation = "S1_LENT"
    elif not has_meta:
        situation = "S2_NO_META"
    elif rating > 0 and rating < 4.0:
        situation = "S5_LOW_RATING"
    elif reviews > 0 and reviews < 30:
        situation = "S3_LOW_REVIEWS"
    elif not has_cta and not tel_link:
        situation = "S6_NO_CTA"
    elif cms in ["wix", "jimdo", "weebly"]:
        situation = "S7_OLD_CMS"
    elif rating >= 4.0 and reviews >= 15:
        # Fallback : bon GMB même si site acceptable → angle GMB
        situation = "S8_GOOD_GMB_BAD_WEB"
    elif not has_meta:
        situation = "S2_NO_META"

    lcp_s = round(lcp_ms / 1000, 1) if lcp_ms else 3.5

    if situation and situation in SITUATIONS_TEMPLATES:
        tmpl = SITUATIONS_TEMPLATES[situation]
        context = {
            "nom": audit_dict.get("nom", "votre établissement"),
            "lcp_s": lcp_s,
            "reviews_count": reviews,
            "rating": rating,
            "cms_detected": cms.capitalize(),
        }
        try:
            argument = tmpl["argument"].format(**context)
        except KeyError:
            argument = tmpl["argument"]

        return {
            "phrase_synthese":  tmpl["label"],
            "diagnostic":       argument,
            "rapport_resume":   argument,
            "service_propose":  main_problem["service_propose"],
        }

    # Aucune situation détectée → retour minimal
    return {
        "phrase_synthese":  "Analyse générale",
        "diagnostic":       main_problem.get("probleme_principal", ""),
        "rapport_resume":   main_problem.get("probleme_principal", ""),
        "service_propose":  main_problem["service_propose"],
    }
