# -*- coding: utf-8 -*-
import os
import sys
import json
import logging
import argparse
from typing import Dict, Any, List

# Configuration des imports pour trouver config_manager.py au root
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(current_dir, ".."))

# Forcer l'encodage UTF-8 pour Windows
if sys.stdout.encoding.lower() != 'utf-8':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

from config_manager import get_sheet, handle_llm_call, check_daily_reset

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
    # --- 8 SITUATIONS STRATÉGIQUES ---
SITUATIONS_TEMPLATES = {
    "S1_LENT": {
        "id": "S1", "label": "Site lent sur mobile",
        "email_objet": "votre site met {lcp_s}s à charger sur mobile",
        "email_corps": "Bonjour {prenom_ou_nom},\n\nJ'ai testé {nom} sur mobile ce matin.\n{lcp_s} secondes avant que la page s'affiche.\n\n53% des visiteurs partent avant 3 secondes.\nVos concurrents chargent en 2s.\nChaque jour, vous perdez la moitié de vos visites mobiles.\n\nVoici ce que j'ai mesuré exactement : [lien rapport]\n\n15 minutes cette semaine ?\n\nJean-Marc",
        "argument": "Votre site charge en {lcp_s}s sur mobile. 53% de vos visiteurs partent avant de voir vos services — soit environ {clients_perdus} clients potentiels perdus chaque mois si vous recevez autant de visites que d'avis."
    },
    "S2_NO_META": {
        "id": "S2", "label": "Pas de meta description",
        "email_objet": "Google invente ce qu'il dit de {nom}",
        "email_corps": "Bonjour {prenom_ou_nom},\n\nQuand quelqu'un cherche {category} à {ville},\nGoogle affiche un texte sous votre lien.\nCe texte, c'est lui qui le choisit — pas vous.\n\nVos concurrents contrôlent ce message.\nVous non.\n\nRésultat : ils ont un taux de clic 2x supérieur au vôtre.\nVoici les données : [lien rapport]\n\nUn appel de 15 minutes ?\n\nJean-Marc",
        "argument": "Votre meta description est absente. Google génère un extrait aléatoire sous votre lien dans les résultats de recherche. Les entreprises qui contrôlent ce texte obtiennent en moyenne 2x plus de clics que leurs concurrents — à position égale."
    },
    "S3_LOW_REVIEWS": {
        "id": "S3", "label": "Peu d'avis Google",
        "email_objet": "{concurrents_avis} avis chez vos concurrents, {reviews_count} chez vous",
        "email_corps": "Bonjour {prenom_ou_nom},\n\nJ'ai cherché {category} à {ville} sur Google.\nLes 3 premiers résultats ont entre {concurrents_avis_min} et {concurrents_avis_max} avis.\n{nom} en a {reviews_count}.\n\nCe n'est pas un problème de qualité.\nC'est un problème de visibilité.\nGoogle classe d'abord ceux qui ont le plus d'avis.\n\nVoici exactement l'écart : [lien rapport]\n\n15 minutes pour en parler ?\n\nJean-Marc",
        "argument": "Avec {reviews_count} avis, {nom} apparaît après des concurrents qui en ont {bench_reviews}+. Google interprète les avis comme un signal de confiance — chaque avis supplémentaire améliore directement votre classement local."
    },
    "S4_NO_SITE": {
        "id": "S4", "label": "Pas de site web",
        "email_objet": "{nom} n'existe pas pour Google",
        "email_corps": "Bonjour {prenom_ou_nom},\n\nJ'ai cherché {category} à {ville} sur Google.\n{nom} a une fiche Google — c'est bien.\nMais il n'y a pas de site web.\n\n85% de vos concurrents en ont un.\nGoogle les favorise dans les résultats.\nVos visiteurs ne peuvent pas en savoir plus sur vous.\n\nJ'ai préparé une analyse de ce que ça vous coûte : [lien]\n\n15 minutes cette semaine ?\n\nJean-Marc",
        "argument": "Sans site web, {nom} est absent de 73% des recherches Google qui aboutissent à un contact. Les entreprises de votre secteur avec un site reçoivent en moyenne 3x plus de demandes de renseignements que celles sans présence web."
    },
    "S5_LOW_RATING": {
        "id": "S5", "label": "Note Google faible",
        "email_objet": "une note de {rating}/5 coûte cher à {nom}",
        "email_corps": "Bonjour {prenom_ou_nom},\n\n{nom} a {rating}/5 sur Google.\nLa référence dans votre secteur à {ville} est 4.5+.\n\n94% des gens lisent les avis avant de choisir.\nSous 4.2, une partie décide d'appeler ailleurs — directement.\n\nCe n'est pas irréversible.\nVoici ce que j'ai analysé : [lien rapport]\n\n15 minutes ?\n\nJean-Marc",
        "argument": "Une note de {rating}/5 fait perdre en moyenne 35% des prospects qui vous trouvent sur Google mais choisissent un concurrent mieux noté. Passer à 4.5+ est réalisable en 3 mois avec une stratégie d'avis structurée."
    },
    "S6_NO_CTA": {
        "id": "S6", "label": "Pas de bouton contact / tel",
        "email_objet": "impossible d'appeler {nom} depuis le site",
        "email_corps": "Bonjour {prenom_ou_nom},\n\nJ'ai visité votre site sur mobile.\nIl n'y a pas de bouton d'appel cliquable.\n\nSur mobile, 70% des visiteurs qui veulent appeler partent s'ils doivent copier-coller un numéro.\nIls appellent le concurrent suivant.\n\nVoici ce que ça représente : [lien rapport]\n\nOn en parle 15 minutes ?\n\nJean-Marc",
        "argument": "Votre site n'a pas de lien téléphonique cliquable sur mobile. 70% des visiteurs mobiles qui cherchent à appeler abandonnent si le numéro n'est pas cliquable. Chaque semaine, des dizaines de prospects potentiels passent à votre concurrent suivant."
    },
    "S7_OLD_CMS": {
        "id": "S7", "label": "CMS vieillot (Wix/Jimdo)",
        "email_objet": "Google pénalise les sites {cms_detected} depuis 2023",
        "email_corps": "Bonjour {prenom_ou_nom},\n\nVotre site est construit sur {cms_detected}.\nCe n'est pas un jugement — c'est un fait technique.\n\nLes sites {cms_detected} chargent en moyenne 2x plus lentement que les sites modernes sur mobile.\nGoogle le mesure et pénalise le classement en conséquence.\n\nJ'ai mesuré votre situation exacte : [lien rapport]\n\n15 minutes pour voir ce que ça change ?\n\nJean-Marc",
        "argument": "Votre site utilise {cms_detected}, une plateforme connue pour ses performances limitées sur mobile. Les sites construits sur des technologies modernes chargent 2x plus vite — Google favorise directement la vitesse dans son algorithme de classement local."
    },
    "S8_GOOD_GMB_BAD_WEB": {
        "id": "S8", "label": "Bon GMB, mauvais site",
        "email_objet": "{reviews_count} avis excellents — site qui ne suit pas",
        "email_corps": "Bonjour {prenom_ou_nom},\n\n{nom} a {rating}/5 avec {reviews_count} avis.\nC'est excellent. Vraiment.\n\nProblème : votre site charge en {lcp_s}s sur mobile.\nUn visiteur qui clique depuis Google arrive sur une page lente.\nLa confiance créée par vos avis s'effondre en 3 secondes.\n\nVoici l'écart entre votre réputation et votre site : [lien]\n\n15 minutes cette semaine ?\n\nJean-Marc",
        "argument": "{nom} a {rating}/5 avec {reviews_count} avis — une réputation exceptionnelle. Mais votre site charge en {lcp_s}s : la moitié des visiteurs partent avant de voir vos services. Vos avis attirent des prospects que votre site fait fuir. C'est le gain le plus rapide disponible."
    }
}

# --- PERSONA JEAN-MARC ---
SYSTEM_PROMPT = """
Tu es Jean-Marc, consultant en visibilité digitale pour les PME locales.
Style direct, sans jargon, pas commercial. 5 phrases max par mail. Signe : Jean-Marc.
"""

def generate_email_content(audit_dict: Dict[str, Any], main_problem: Dict[str, str]) -> Dict[str, Any]:
    """Appel LLM avec Jean-Marc, mais priorité aux 8 situations stratégiques."""
    
    # 1. Détection de la situation stratégique
    m_score = audit_dict.get('mobile_score', 100)
    lcp_ms = audit_dict.get('lcp_ms', 0)
    rating = audit_dict.get('rating', 0)
    reviews = audit_dict.get('reviews_count', 0)
    has_meta = audit_dict.get('has_meta_description', True)
    has_site = audit_dict.get('site_web') is not None
    has_cta = audit_dict.get('has_contact_button', True)
    tel_link = audit_dict.get('tel_link', True)
    cms = str(audit_dict.get('cms_detected', "")).lower()

    situation = None
    
    # Ordre de priorité des situations
    if not has_site: situation = "S4_NO_SITE"
    elif rating >= 4.5 and reviews >= 50 and m_score < 60: situation = "S8_GOOD_GMB_BAD_WEB"
    elif lcp_ms > 4000 and m_score < 55: situation = "S1_LENT"
    elif not has_meta: situation = "S2_NO_META"
    elif rating > 0 and rating < 4.0: situation = "S5_LOW_RATING"
    elif reviews > 0 and reviews < 20: situation = "S3_LOW_REVIEWS"
    elif not has_cta and not tel_link: situation = "S6_NO_CTA"
    elif cms in ["wix", "jimdo", "weebly"]: situation = "S7_OLD_CMS"

    if situation and situation in SITUATIONS_TEMPLATES:
        tmpl = SITUATIONS_TEMPLATES[situation]
        
        # Préparation des variables
        lcp_s = round(lcp_ms / 1000, 1) if lcp_ms else 3.5
        clients_perdus = int(reviews * 0.53)
        
        # Estimation concurrents (à affiner si on a le top3)
        # On peut fixer des valeurs par défaut pour le test
        concurrents_avis = 85
        concurrents_avis_min = 45
        concurrents_avis_max = 120
        bench_reviews = 50

        # Remplacement manuel dans les templates
        context = {
            "nom": audit_dict.get("nom", "votre établissement"),
            "prenom_ou_nom": audit_dict.get("nom", "votre établissement"), # Fallback sur le nom de l'établissement pour l'instant
            "ville": audit_dict.get("ville", "votre ville"),
            "category": audit_dict.get("category", "votre secteur"),
            "lcp_s": lcp_s,
            "reviews_count": reviews,
            "rating": rating,
            "cms_detected": cms.capitalize(),
            "clients_perdus": clients_perdus,
            "concurrents_avis": concurrents_avis,
            "concurrents_avis_min": concurrents_avis_min,
            "concurrents_avis_max": concurrents_avis_max,
            "bench_reviews": bench_reviews
        }

        email_objet = tmpl["email_objet"].format(**context)
        email_corps = tmpl["email_corps"].format(**context)
        argument_unique = tmpl["argument"].format(**context)

        return {
            "phrase_synthese": tmpl["label"],
            "diagnostic": argument_unique,
            "opportunite": [argument_unique, "Optimisation de la conversion mobile", "Sécurisation de la réputation Google"],
            "rapport_resume": argument_unique,
            "email_objet": email_objet,
            "email_corps": email_corps,
            "service_propose": main_problem["service_propose"]
        }

    # Si aucune situation type, fallback sur le LLM comme avant
    if main_problem["service_propose"] == "Aucun":
        return {"rapport_resume": "R.A.S.", "email_objet": "audit", "email_corps": "R.A.S."}
    
    tech_metrics = f"""
    MÉTRIQUES : Mobile {m_score}/100, LCP {lcp_ms}ms, 
    SEO Meta {'OK' if has_meta else 'KO'}, GMB {rating}/5.
    """
    
    user_prompt = f"""
    Établissement : {audit_dict.get('nom')} à {audit_dict.get('ville')}
    PROBLÈME : {main_problem['probleme_principal']}
    SERVICE : {main_problem['service_propose']}
    {tech_metrics}
    
    Génère le JSON : phrase_synthese, obs_mobile, impact_mobile, obs_seo, impact_seo, obs_gmb, impact_gmb, diagnostic, opportunite (liste), rapport_resume, email_objet, email_corps.
    """
    try:
        res = handle_llm_call(prompt=user_prompt, system=SYSTEM_PROMPT)
        text = res.strip()
        if "```json" in text: text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text: text = text.split("```")[1].split("```")[0].strip()
        reponse_json = json.loads(text)
        reponse_json["service_propose"] = main_problem["service_propose"]
        return reponse_json
    except Exception as e:
        logger.error(f"Erreur Jean-Marc LLM: {e}")
        return {"service_propose": "Erreur LLM", "rapport_resume": "Erreur génération."}

def process_copywriter(limit=None):
    """Traitement par lots des leads audités techniquement."""
    sheet = get_sheet("Leads")
    all_rows = sheet.get_all_values()
    if not all_rows: return
    headers = all_rows[0]
    
    processed = 0
    for i, row in enumerate(all_rows[1:]):
        row_num = i + 2
        data = dict(zip(headers, row))
        
        # On traite si l'audit technique est là mais pas Jean-Marc
        if data.get("Résultats Technique") and not data.get("Service Proposé"):
            print(f"   [Agent Jean-Marc] Analyse de {data.get('Nom')}...")
            
            # Reconstruction de l'objet audit
            try:
                full_audit = json.loads(data.get("JSON Complet", "{}"))
            except:
                full_audit = data
            
            impacts = get_all_impacts(full_audit)
            problemes = extract_problemes_detectes(impacts, full_audit)
            main_prob = determine_main_problem(problemes, impacts)
            
            full_audit["problemes_detectes"] = problemes
            full_audit["probleme_principal"] = main_prob["probleme_principal"]
            
            copy_res = generate_email_content(full_audit, main_prob)
            full_audit.update(copy_res)
            
            # Mise à jour Sheets
            col_service = headers.index("Service Proposé") + 1
            col_mail = headers.index("Corps Email") + 1
            col_json = headers.index("JSON Complet") + 1
            
            sheet.update_cell(row_num, col_service, copy_res.get("service_propose"))
            sheet.update_cell(row_num, col_mail, copy_res.get("email_corps"))
            sheet.update_cell(row_num, col_json, json.dumps(full_audit, ensure_ascii=False))
            
            processed += 1
            if limit and processed >= limit: break
            
    print(f"[Terminé] Copywriting terminé pour {processed} lead(s).")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    process_copywriter(args.limit)
