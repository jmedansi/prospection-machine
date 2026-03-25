# -*- coding: utf-8 -*-
import os
import sys
import shutil
import asyncio
import logging
import json
import argparse
import base64
from datetime import datetime
from typing import Dict, Any, List
from types import SimpleNamespace
from jinja2 import Environment, FileSystemLoader
from playwright.async_api import async_playwright

# Configuration des imports pour trouver config_manager.py au root
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(current_dir, ".."))

from config_manager import get_sheet

# Configuration du logger
logging.basicConfig(
    filename='errors.log',
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Forcer l'encodage UTF-8 pour Windows
if sys.stdout.encoding.lower() != 'utf-8':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

# --- BASE DE DONNÉES BENCHMARKS ---
BENCHMARKS = {
  "restaurant": {
    "label": "Restauration",
    "lcp_ms":          {"bon": 2000, "moyen": 3500,  "ref_label": "< 2.0s"},
    "mobile_score":    {"bon": 75,   "moyen": 55,    "ref_label": "75+"},
    "reviews_count":   {"bon": 100,  "moyen": 30,    "ref_label": "> 100 avis"},
    "rating":          {"bon": 4.5,  "moyen": 4.0,   "ref_label": "> 4.5 ⭐"},
    "photos_count":    {"bon": 30,   "moyen": 10,    "ref_label": "> 30 photos"},
    "page_size_kb":    {"bon": 1200, "moyen": 2500,  "ref_label": "< 1 200 Ko"},
    "insight": "Les restaurants avec 100+ avis Google reçoivent 3x plus de réservations en ligne.",
    "insight_seo": "70% des recherches 'restaurant [ville]' aboutissent à un clic sur les 3 premiers résultats Maps.",
    "insight_speed": "Un restaurant qui charge en moins de 2s convertit 2x plus de visiteurs en réservations.",
  },
  "juridique": {
    "label": "Cabinet Juridique",
    "lcp_ms":          {"bon": 2500, "moyen": 4000,  "ref_label": "< 2.5s"},
    "mobile_score":    {"bon": 70,   "moyen": 50,    "ref_label": "70+"},
    "reviews_count":   {"bon": 50,   "moyen": 20,    "ref_label": "> 50 avis"},
    "rating":          {"bon": 4.5,  "moyen": 4.0,   "ref_label": "> 4.5 ⭐"},
    "photos_count":    {"bon": 15,   "moyen": 5,     "ref_label": "> 15 photos"},
    "page_size_kb":    {"bon": 1500, "moyen": 3000,  "ref_label": "< 1 500 Ko"},
    "insight": "83% des personnes cherchant un avocat commencent leur recherche sur Google.",
    "insight_seo": "Les cabinets avec Schema.org configuré apparaissent 40% plus souvent en position zéro.",
    "insight_speed": "53% des visiteurs mobiles quittent un site juridique qui charge en plus de 3 secondes.",
  },
  "sante": {
    "label": "Santé & Médical",
    "lcp_ms":          {"bon": 2000, "moyen": 3500,  "ref_label": "< 2.0s"},
    "mobile_score":    {"bon": 75,   "moyen": 55,    "ref_label": "75+"},
    "reviews_count":   {"bon": 80,   "moyen": 25,    "ref_label": "> 80 avis"},
    "rating":          {"bon": 4.6,  "moyen": 4.2,   "ref_label": "> 4.6 ⭐"},
    "photos_count":    {"bon": 20,   "moyen": 8,     "ref_label": "> 20 photos"},
    "page_size_kb":    {"bon": 1200, "moyen": 2500,  "ref_label": "< 1 200 Ko"},
    "insight": "77% des patients consultent les avis Google avant de choisir un médecin.",
    "insight_seo": "Les pages médicales avec Schema.org LocalBusiness ont 35% de clics supplémentaires.",
    "insight_speed": "Un patient qui attend plus de 3s abandonne et consulte le concurrent suivant.",
  },
  "beaute": {
    "label": "Beauté & Bien-être",
    "lcp_ms":          {"bon": 2000, "moyen": 3000,  "ref_label": "< 2.0s"},
    "mobile_score":    {"bon": 80,   "moyen": 60,    "ref_label": "80+"},
    "reviews_count":   {"bon": 80,   "moyen": 25,    "ref_label": "> 80 avis"},
    "rating":          {"bon": 4.7,  "moyen": 4.3,   "ref_label": "> 4.7 ⭐"},
    "photos_count":    {"bon": 40,   "moyen": 15,    "ref_label": "> 40 photos"},
    "page_size_kb":    {"bon": 1500, "moyen": 3000,  "ref_label": "< 1 200 Ko"},
    "insight": "Les salons avec 40+ photos Google reçoivent 89% de demandes de contact en plus.",
    "insight_seo": "60% des réservations beauté viennent d'une recherche Google Maps mobile.",
    "insight_speed": "L'industrie beauté a le taux d'abandon mobile le plus élevé : 58% après 3s.",
  },
  "immobilier": {
    "label": "Immobilier",
    "lcp_ms":          {"bon": 2500, "moyen": 4000,  "ref_label": "< 2.5s"},
    "mobile_score":    {"bon": 70,   "moyen": 50,    "ref_label": "70+"},
    "reviews_count":   {"bon": 40,   "moyen": 15,    "ref_label": "> 40 avis"},
    "rating":          {"bon": 4.5,  "moyen": 4.0,   "ref_label": "> 4.5 ⭐"},
    "photos_count":    {"bon": 20,   "moyen": 8,     "ref_label": "> 20 photos"},
    "page_size_kb":    {"bon": 2000, "moyen": 4000,  "ref_label": "< 2 000 Ko"},
    "insight": "Les agences immobilières avec des avis Google actifs convertissent 2.4x plus de mandats.",
    "insight_seo": "Les biens présentés sur des pages SEO optimisées se vendent 18% plus vite.",
    "insight_speed": "68% des acheteurs immobiliers cherchent sur mobile — vitesse = premier filtre.",
  },
  "commerce": {
    "label": "Commerce & Retail",
    "lcp_ms":          {"bon": 1800, "moyen": 3000,  "ref_label": "< 1.8s"},
    "mobile_score":    {"bon": 80,   "moyen": 60,    "ref_label": "80+"},
    "reviews_count":   {"bon": 60,   "moyen": 20,    "ref_label": "> 60 avis"},
    "rating":          {"bon": 4.5,  "moyen": 4.0,   "ref_label": "> 4.5 ⭐"},
    "photos_count":    {"bon": 25,   "moyen": 8,     "ref_label": "> 25 photos"},
    "page_size_kb":    {"bon": 1500, "moyen": 3000,  "ref_label": "< 1 500 Ko"},
    "insight": "1 seconde de délai supplémentaire réduit les conversions e-commerce de 7%.",
    "insight_seo": "Les fiches Google avec photos produits génèrent 42% de clics supplémentaires.",
    "insight_speed": "Un site commerce rapide retient 3x plus de visiteurs que la moyenne du secteur.",
  },
  "agence": {
    "label": "Agence & Services B2B",
    "lcp_ms":          {"bon": 2500, "moyen": 4000,  "ref_label": "< 2.5s"},
    "mobile_score":    {"bon": 70,   "moyen": 50,    "ref_label": "70+"},
    "reviews_count":   {"bon": 30,   "moyen": 10,    "ref_label": "> 30 avis"},
    "rating":          {"bon": 4.6,  "moyen": 4.2,   "ref_label": "> 4.6 ⭐"},
    "photos_count":    {"bon": 15,   "moyen": 5,     "ref_label": "> 15 photos"},
    "page_size_kb":    {"bon": 1500, "moyen": 3000,  "ref_label": "< 1 500 Ko"},
    "insight": "67% des acheteurs B2B consultent le site web avant tout premier contact.",
    "insight_seo": "Les agences avec blog actif génèrent 3x plus de leads inbound.",
    "insight_speed": "Un site B2B lent signale un manque de professionnalisme avant même le premier appel.",
  },
  "hotellerie": {
    "label": "Hôtellerie",
    "lcp_ms":        {"bon": 2000, "moyen": 3500, "ref_label": "< 2.0s"},
    "mobile_score":  {"bon": 75,   "moyen": 55,   "ref_label": "75+"},
    "reviews_count": {"bon": 200,  "moyen": 50,   "ref_label": "> 200 avis"},
    "rating":        {"bon": 4.5,  "moyen": 4.0,  "ref_label": "> 4.5 ⭐"},
    "photos_count":  {"bon": 50,   "moyen": 20,   "ref_label": "> 50 photos"},
    "page_size_kb":  {"bon": 2000, "moyen": 4000, "ref_label": "< 2 000 Ko"},
    "insight": "95% des voyageurs consultent les avis en ligne avant de réserver un hôtel.",
    "insight_seo": "Les hôtels avec Schema.org Hotel configuré apparaissent dans les rich results Google.",
    "insight_speed": "Un hôtel dont le site charge en moins de 2s convertit 3x plus de réservations directes.",
  },
  "default": {
    "label": "Commerce Local",
    "lcp_ms":          {"bon": 2500, "moyen": 4000,  "ref_label": "< 2.5s"},
    "mobile_score":    {"bon": 70,   "moyen": 50,    "ref_label": "70+"},
    "reviews_count":   {"bon": 50,   "moyen": 15,    "ref_label": "> 50 avis"},
    "rating":          {"bon": 4.5,  "moyen": 4.0,   "ref_label": "> 4.5 ⭐"},
    "photos_count":    {"bon": 15,   "moyen": 5,     "ref_label": "> 15 photos"},
    "page_size_kb":    {"bon": 1500, "moyen": 3000,  "ref_label": "< 1 500 Ko"},
    "insight": "Les entreprises locales avec profil Google complet reçoivent 70% de visites en plus.",
    "insight_seo": "46% de toutes les recherches Google ont une intention locale.",
    "insight_speed": "53% des visiteurs mobiles abandonnent un site qui charge en plus de 3 secondes.",
  }
}

SECTOR_KEYWORDS = {
  "restaurant": ["restaurant","brasserie","café","bar","pizzeria","sushi","burger","traiteur","boulangerie","pâtisserie"],
  "juridique":  ["avocat","cabinet","juridique","notaire","huissier","barreau","law","legal"],
  "sante":      ["médecin","docteur","clinique","dentiste","kiné","pharmacie","ostéo","ophtalmo","dermato","médical"],
  "beaute":     ["salon", "coiffeur", "coiffure", "beauté", "spa", "esthétique", "onglerie", "barbier", "barbershop", "massage", "bien-être", "institut", "nail"],
  "bijouterie": ["bijouterie", "bijoux", "joaillerie", "joaillier", "horlogerie", "montre", "diamant", "bague", "collier", "bracelet", "orfèvrerie", "goldsmith"],
  "immobilier": ["immobilier","agence","promoteur","logement","appartement","maison","location","vente"],
  "commerce":   ["boutique","magasin","shop","retail","vêtements","chaussures","épicerie","supermarché"],
  "agence":     ["agence","conseil","consulting","digital","web","marketing","communication","design","studio"],
  "hotellerie": ["hôtel", "hotel", "auberge", "chambres d'hôtes", "bed and breakfast", "b&b", "résidence", "gîte", "hébergement", "lodge", "resort"],
}

# --- LOGIQUE MÉTIER ---
def detect_sector(category: str) -> str:
    category_lower = category.lower() if category else ""
    for sector, keywords in SECTOR_KEYWORDS.items():
        if any(kw in category_lower for kw in keywords):
            return sector
    return "default"

def get_status(value, metric: str, benchmarks: dict) -> dict:
    bench = benchmarks.get(metric)
    if not bench or value is None: 
        return {"statut": "⚠️ Donnée indisponible", "couleur": "#6b7280", "ecart": "Scan incomplet"}
    
    inverted = ["lcp_ms", "page_size_kb", "render_blocking_scripts", "images_without_alt"]
    val = float(value)
    if metric in inverted:
        if val <= bench["bon"]:
            statut, couleur = "✅ Excellent", "#16a34a"
            ecart = f"{bench['bon'] - val:+.0f} sous la réf."
        elif val <= bench["moyen"]:
            statut, couleur = "⚠️ Moyen", "#d97706"
            ecart = f"{val - bench['bon']:+.0f} au-dessus"
        else:
            statut, couleur = "🔴 Critique", "#dc2626"
            ecart = f"{val - bench['bon']:+.0f} au-dessus"
    else:
        if val >= bench["bon"]:
            statut, couleur = "✅ Excellent", "#16a34a"
            ecart = f"{val - bench['bon']:+.1f} au-dessus"
        elif val >= bench["moyen"]:
            statut, couleur = "⚠️ Moyen", "#d97706"
            ecart = f"{bench['bon'] - val:+.1f} sous la réf."
        else:
            statut, couleur = "🔴 Critique", "#dc2626"
            ecart = f"{bench['bon'] - val:+.1f} sous la réf."
    return {"statut": statut, "couleur": couleur, "ecart": ecart, "ref_label": bench["ref_label"]}

def enrich_data(audit_data: dict) -> dict:
    sector_key = detect_sector(audit_data.get("category", ""))
    benchmarks = BENCHMARKS[sector_key]
    data = audit_data.copy()
    MOIS_FR = {
      1:"Janvier", 2:"Février", 3:"Mars", 4:"Avril",
      5:"Mai", 6:"Juin", 7:"Juillet", 8:"Août",
      9:"Septembre", 10:"Octobre", 11:"Novembre", 12:"Décembre"
    }
    now = datetime.now()
    data["date_audit"] = f"{now.day} {MOIS_FR[now.month]} {now.year}"
    data["sector_label"] = benchmarks["label"]
    numeric_metrics = ["lcp_ms", "mobile_score", "reviews_count", "rating", "photos_count", "page_size_kb", "render_blocking_scripts", "images_without_alt"]
    metrics_dict = {}
    for metric in numeric_metrics:
        val = audit_data.get(metric)
        metrics_dict[metric] = {"valeur": val, **get_status(val, metric, benchmarks)}
    data["metrics"] = SimpleNamespace(**{k: SimpleNamespace(**v) if isinstance(v, dict) else v for k, v in metrics_dict.items()})
    bool_metrics = {
        "has_https": ("HTTPS", "Obligatoire"), "has_meta_description": ("Meta Description", "Obligatoire"),
        "has_contact_button": ("Bouton Contact", "Recommandé"), "tel_link": ("Tél. Cliquable", "Recommandé"),
        "has_schema": ("Schema.org", "Recommandé"), "uses_cache": ("Cache Navigateur", "Recommandé"), "has_analytics": ("Analytics", "Recommandé"),
    }
    bool_metrics_dict = {}
    for key, (label, ref) in bool_metrics.items():
        val = audit_data.get(key)
        bool_metrics_dict[key] = {
            "label": label, "valeur": val, "statut": "✅ Actif" if val else "🔴 Absent",
            "couleur": "#16a34a" if val else "#dc2626", "ref_label": ref
        }
    data["bool_metrics"] = {}
    for key, (label, ref) in bool_metrics.items():
        val = audit_data.get(key)
        data["bool_metrics"][key] = {
            "label": label, "valeur": val, "statut": "✅ Actif" if val else "🔴 Absent",
            "couleur": "#16a34a" if val else "#dc2626", "ref_label": ref
        }
    data["insight_gmb"], data["insight_seo"], data["insight_speed"] = benchmarks["insight"], benchmarks["insight_seo"], benchmarks["insight_speed"]
    # Performance
    m_score_raw = audit_data.get("mobile_score")
    m_score = int(m_score_raw) if m_score_raw is not None else 0
    d_score_raw = audit_data.get("desktop_score")
    if d_score_raw is not None:
        d_score = int(d_score_raw)
    else:
        d_score = int(m_score * 1.2) if m_score < 70 else m_score
    
    t_score = int((m_score + d_score) / 2)
    
    data["insight_gmb"] = benchmarks["insight"]
    data["insight_seo"] = benchmarks["insight_seo"]
    data["insight_speed"] = benchmarks["insight_speed"]
    data["benchmarks"] = benchmarks
    
    data["mobile_score"] = m_score
    data["desktop_score"] = min(98, d_score)
    data["tablet_score"] = t_score
    
    data["grade_performance"] = "A" if m_score and m_score >= 90 else "B" if m_score and m_score >= 70 else "C" if m_score and m_score >= 50 else "D" if m_score and m_score >= 30 else "F" if m_score is not None else "F"
    
    # SEO
    has_meta = audit_data.get("has_meta_description", False)
    data["seo_score"] = 85 if has_meta else 40
    data["grade_seo"] = "B" if has_meta else "F"
    
    # GMB
    rating_raw = audit_data.get("rating")
    rating = float(rating_raw) if rating_raw is not None else 0.0
    
    data["rating"] = rating
    data["gmb_score"] = int(rating / 5 * 100) if rating is not None else 0
    data["grade_gmb"] = "A" if rating and rating >= 4.7 else "B" if rating and rating >= 4.2 else "C" if rating and rating >= 3.5 else "D"
    
    # UX
    m_score_val = m_score if m_score is not None else 0
    data["grade_ux"] = "A" if m_score_val >= 85 else "B" if m_score_val >= 65 else "C" if m_score_val >= 45 else "D"
    
    # Valeurs brutes pour le template
    data["lcp_ms"] = int(float(audit_data.get("lcp_ms", 3000)))
    data["fcp_ms"] = int(float(audit_data.get("fcp_ms", data["lcp_ms"] * 0.6)))
    data["cls"] = float(audit_data.get("cls", 0.14))
    data["render_blocking_scripts"] = int(audit_data.get("render_blocking_scripts", 0))
    data["page_size_kb"] = int(audit_data.get("page_size_kb", 1500))
    data["meta_description_extract"] = audit_data.get("meta_description", "")
    data["title_length"] = int(audit_data.get("title_length", 0))

    # --- Logique de Dynamisation Avancée (User Request) ---
    def get_color_score(v):
        if v >= 70: return "#16a34a" # Vert
        if v >= 50: return "#d97706" # Orange
        return "#dc2626" # Rouge

    # Couleurs des scores terminaux
    data["couleur_mobile"] = get_color_score(data["mobile_score"])
    data["couleur_desktop"] = get_color_score(data["desktop_score"])
    data["couleur_tablet"] = get_color_score(data["tablet_score"])
    
    # Couleurs des jauges
    data["couleur_seo"] = get_color_score(data["seo_score"])
    data["couleur_gmb"] = get_color_score(data["gmb_score"])

    # Couleurs CWV
    f_ms = data.get("fcp_ms", 3000)
    data["couleur_fcp"] = "#16a34a" if f_ms < 1800 else "#d97706" if f_ms < 3000 else "#dc2626"
    
    c_ls = data.get("cls", 0)
    data["couleur_cls"] = "#16a34a" if c_ls < 0.1 else "#d97706" if c_ls < 0.25 else "#dc2626"

    # Variables pour jauges CSS (0-100)
    data["gauge_perf_pct"] = data["mobile_score"]
    data["gauge_seo_pct"] = data["seo_score"]
    data["gauge_gmb_pct"] = data["gmb_score"]

    # Traitement URL (SERP)
    site_web_raw = audit_data.get("site_web") or ""
    site_web_clean = site_web_raw.rstrip('/')
    data["display_url"] = site_web_clean.replace('https://', '').replace('http://', '') if site_web_clean else "pas-de-site.com"

    # Mapping métier pour Jean-Marc (verdict)
    mapping = {
        "Optimisation SEO": "SÉO LOCAL",
        "Optimisation GMB": "GOOGLE MAPS",
        "Performance Mobile": "PERFORMANCE"
    }
    
    # Arguments dynamiques selon template_used
    template_used = audit_data.get("template_used", "audit")
    thomas_opps = audit_data.get("opportunite", [])
    
    if not thomas_opps:
        if template_used == "reputation":
            thomas_opps = [
                f"Stratégie Avis — Votre note de {rating}/5 est en dessous du standard ({benchmarks.get('bench_rating', 4.6)}/5).",
                "Photos & Visibilité — Les fiches avec 10+ photos reçoivent 2x plus de clics.",
                "Réponses & Engagement — Répondre aux avis augmente votre crédibilité locale."
            ]
        elif template_used == "maquette":
            thomas_opps = [
                "Presence Numerique — 85% des recherches locales menent a une action dans les 24h.",
                "Visibilite Google — Sans site, vous perdez des clients au profit de vos concurrents.",
                "Credibilite — Un site web renforce la confiance avant meme du premier contact."
            ]
        elif template_used == "seo":
            thomas_opps = [
                "Referencement Google — Votre site n'apparait pas sur les mots-cles qui comptent pour votre activite.",
                "Meta Description — Absente, vous perdez 30% de clics depuis les moteurs de recherche.",
                "Schema.org — Absent, vous perdez des rich snippets qui attirent l'attention dans les resultats.",
                "Performance — La vitesse de chargement affecte aussi votre classement Google."
            ]
        else:  # audit ou fallback
            m_score_val = int(float(audit_data.get("mobile_score", 0)))
            lcp_val = int(float(audit_data.get("lcp_ms", 3000)))
            thomas_opps = [
                f"Performance Mobile — Score {m_score_val}/100, vos visiteurs repartent sans voir votre offre.",
                f"Vitesse Chargement — LCP de {lcp_val}ms, au-dela des 3 secondes recommandees.",
                "Referencement — Meme rapide, un site mal reference ne sera pas trouve sur Google.",
                "Conversion — Un site lent perd 53% des visiteurs avant qu'ils ne convertissent."
            ]
    
    data["arguments"] = thomas_opps[:3]

    # Score Priorité & Urgence
    score = float(audit_data.get("score_priorite", 5))
    # Si non fourni, on peut l'estimer grossièrement par l'inverse du mobile_score
    if not audit_data.get("score_priorite"):
        m_score_calc = int(float(audit_data.get("mobile_score", 0)))
        score = max(1, 10 - (m_score_calc // 10))
    
    data["score_priorite"] = score
    if score >= 7: data["score_couleur"], data["score_label"] = "#dc2626", "Priorité Haute"
    elif score >= 4: data["score_couleur"], data["score_label"] = "#d97706", "À optimiser"
    else: data["score_couleur"], data["score_label"] = "#16a34a", "Bonne base"

    data["has_site"] = audit_data.get("site_web") not in [None, "", "sans_site", "SANS SITE"]
    data["lien_calendly"] = "https://calendly.com/jmedansi/15min"
    data["benchmarks"] = benchmarks
    
    # Couleurs et classes (Profil B technique)
    def get_color(score):
        if score >= 80: return "#16a34a"
        if score >= 50: return "#d97706"
        return "#dc2626"
    
    def get_color_class(score):
        if score >= 80: return "vert"
        if score >= 50: return "orange"
        return "rouge"

    data["couleur_mobile"] = get_color(data["mobile_score"])
    data["couleur_desktop"] = get_color(data["desktop_score"])
    data["couleur_seo"] = get_color(data["seo_score"])
    
    data["couleur_mobile_class"] = get_color_class(data["mobile_score"])
    data["couleur_desktop_class"] = get_color_class(data["desktop_score"])
    
    data["couleur_grade_perf"] = get_color(data["mobile_score"])
    data["couleur_grade_seo"] = get_color(data["seo_score"])
    data["couleur_grade_gmb"] = get_color(data["gmb_score"])
    
    # Urgence
    score_pri = audit_data.get("score_priorite", audit_data.get("score_urgence", 5))
    data["score_priorite"] = score_pri
    data["urgency_color"] = get_color_class((10 - score_pri) * 10) # Inverse car score haut = rouge
    data["couleur_grade_global"] = get_color((10 - score_pri) * 10)
    data["grade_global"] = "A" if score_pri < 3 else "B" if score_pri < 5 else "C" if score_pri < 7 else "D"

    # Verdict
    if score_pri >= 7:
        data["verdict"] = "Urgence critique : Votre site bride actuellement votre croissance. Une intervention technique immédiate est recommandée."
    elif score_pri >= 4:
        data["verdict"] = "Optimisation nécessaire : Plusieurs freins techniques empêchent votre site d'atteindre son plein potentiel."
    else:
        data["verdict"] = "Bonne santé : Votre site dispose d'une base technique solide, quelques optimisations légères suffiront."

    # Métriques détaillées
    data["lcp_ms"] = int(float(audit_data.get("lcp_ms", 3000)))
    data["couleur_lcp"] = "#16a34a" if data["lcp_ms"] < 2500 else "#d97706" if data["lcp_ms"] < 4000 else "#dc2626"
    
    data["fcp_ms"] = int(float(audit_data.get("fcp_ms", 1800)))
    data["couleur_fcp"] = "#16a34a" if data["fcp_ms"] < 1800 else "#d97706" if data["fcp_ms"] < 3000 else "#dc2626"
    
    data["cls"] = float(audit_data.get("cls", 0.1))
    data["couleur_cls"] = "#16a34a" if data["cls"] < 0.1 else "#d97706" if data["cls"] < 0.25 else "#dc2626"
    
    data["render_blocking_scripts"] = int(audit_data.get("render_blocking_scripts", 0))
    # Merge render_blocking_scripts into existing metrics SimpleNamespace
    data["metrics"].render_blocking_scripts = SimpleNamespace(
        couleur="#16a34a" if data["render_blocking_scripts"] == 0 else "#d97706" if data["render_blocking_scripts"] < 3 else "#dc2626"
    )
    
    data["display_url"] = (audit_data.get("site_web") or "").replace("https://", "").replace("http://", "").split("/")[0]
    data["has_site"] = data["has_site"]
    data["lien_calendly"] = "https://calendly.com/jmedansi/15min"
    return data

# --- GÉNÉRATION HTML & PUBLICATION ---

async def generate_and_publish_report(audit_data: Dict[str, Any]) -> str:
    """
    Génère le rapport HTML selon le profil et le publie sur Vercel.
    Retourne l'URL publique.
    """
    from synthetiseur.vercel_publisher import publish_to_vercel, generate_slug
    
    nom = audit_data.get("nom", "Prospect")
    lead_id = audit_data.get("lead_id") or audit_data.get("id") or generate_slug(audit_data.get("nom", "unknown"))
    
    # Enrichissement des données
    enriched = enrich_data(audit_data)
    
    # Sélection du template
    template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates', 'rapports')
    env = Environment(loader=FileSystemLoader(template_dir))
    
    template_used = audit_data.get("template_used", "audit")
    
    # Mapping spécifique selon le template
    if template_used == "reputation" or audit_data.get("profil") == "C":
        # Template utilisateur : rapport-profil-c-gmb.html
        template = env.get_template("rapport-profil-c-gmb.html")
        # Variables en majuscules pour ce template
        rating = enriched.get("rating", 0)
        reviews = enriched.get("reviews_count", 0)
        photos = enriched.get("photos_count", 0)
        
        # Calcul des pourcentages pour les barres (sur 5 pour rating, sur 100 pour avis/photos max arbitraire)
        mapping_data = {
            "NOM": nom,
            "VILLE": enriched.get("ville", ""),
            "SECTEUR": enriched.get("sector_label", "Entreprise"),
            "RATING": rating,
            "REVIEWS": reviews,
            "PHOTOS": photos,
            "RATING_PCT": min(100, (rating / 5) * 100) if rating else 0,
            "REVIEWS_PCT": min(100, (reviews / 50) * 100) if reviews else 0, # Bench à 50
            "PHOTOS_PCT": min(100, (photos / 20) * 100) if photos else 0,   # Bench à 20
            "BENCH_RATING": 4.6,
            "BENCH_REVIEWS": 87,
            "BENCH_PHOTOS": 45,
            "ARG1": enriched["arguments"][0] if enriched["arguments"] else "",
            "ARG2": enriched["arguments"][1] if len(enriched["arguments"]) > 1 else "",
            "ARG3": enriched["arguments"][2] if len(enriched["arguments"]) > 2 else "",
            "DATE": enriched["date_audit"],
            "LIEN_CALENDLY": "https://calendly.com/jmedansi/15min"
        }
    elif template_used == "maquette" or not enriched.get("has_site"):
        # Maquette = uniquement si pas de site (sinon c'est une erreur de template_used)
        template = env.get_template("rapport-profil-a-maquette.html")
        mapping_data = enriched
    elif template_used == "seo":
        # SEO - reutilise le template technique avec arguments SEO
        template = env.get_template("rapport-profil-b-technique.html")
        mapping_data = enriched
    elif template_used == "audit":
        # Template Technique
        template = env.get_template("rapport-profil-b-technique.html")
        mapping_data = enriched
    else:
        # Fallback: Template Technique
        template = env.get_template("rapport-profil-b-technique.html")
        mapping_data = enriched

    # Screenshots pour upload Vercel
    screenshots = {}
    site_url = audit_data.get("site_web", "")
    
    # Récupérer les screenshots depuis la base ou le générateur de maquette
    desktop_path = audit_data.get("screenshot_desktop", "") or enriched.get("screenshot_desktop", "")
    mobile_path = audit_data.get("screenshot_mobile", "") or enriched.get("screenshot_mobile", "")
    
    if not desktop_path and site_url and enriched.get("has_site"):
        try:
            import asyncio
            from playwright.async_api import async_playwright
            reports_dir = os.path.join(os.path.dirname(__file__), "reports")
            os.makedirs(reports_dir, exist_ok=True)
            
            async def capture_screenshots_for_report():
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True)
                    
                    # Screenshot Desktop
                    desktop_path = os.path.join(reports_dir, f"desktop_{lead_id}.png")
                    page = await browser.new_page(viewport={'width': 1280, 'height': 800})
                    try:
                        await page.goto(site_url, timeout=15000, wait_until="networkidle")
                        await page.screenshot(path=desktop_path, full_page=False)
                    except Exception as e:
                        logger.warning(f"Desktop screenshot failed: {e}")
                        desktop_path = None
                    await page.close()
                    
                    # Screenshot Mobile
                    mobile_path = os.path.join(reports_dir, f"mobile_{lead_id}.png")
                    page = await browser.new_page(viewport={'width': 375, 'height': 812})
                    try:
                        await page.goto(site_url, timeout=15000, wait_until="networkidle")
                        await page.screenshot(path=mobile_path, full_page=False)
                    except Exception as e:
                        logger.warning(f"Mobile screenshot failed: {e}")
                        mobile_path = None
                    await page.close()
                    
                    await browser.close()
                    return desktop_path, mobile_path
            
            desktop_path, mobile_path = await capture_screenshots_for_report()
        except Exception as e:
            logger.warning(f"Screenshot capture failed: {e}")
            desktop_path = None
            mobile_path = None
    
    slug = generate_slug(nom)
    
    if desktop_path and os.path.exists(desktop_path):
        screenshots["screenshot_desktop"] = desktop_path
        mapping_data["screenshot_desktop"] = f"https://audit.incidenx.com/{slug}/{os.path.basename(desktop_path)}"
    if mobile_path and os.path.exists(mobile_path):
        screenshots["screenshot_mobile"] = mobile_path
        mapping_data["screenshot_mobile"] = f"https://audit.incidenx.com/{slug}/{os.path.basename(mobile_path)}"
    
    html_content = template.render(**mapping_data)
    
    # Sauvegarder le HTML en base
    lead_id = audit_data.get('lead_id') or audit_data.get('id')
    
    slug = generate_slug(nom)
    preview_dir = os.path.join(reports_dir, slug)
    
    # Créer le dossier local pour le rapport (sans nettoyer pour éviter de perdre les anciens fichiers si la génération échoue)
    os.makedirs(preview_dir, exist_ok=True)
    
    # Copier les screenshots dans le dossier du slug
    for key, local_path in screenshots.items():
        if local_path and os.path.exists(local_path):
            filename = os.path.basename(local_path)
            dest_path = os.path.join(preview_dir, filename)
            shutil.copy2(local_path, dest_path)
            logger.error(f"[REPORTER] Copié {filename} vers {preview_dir}")
    
    # Remplacer les URLs dans le HTML pour utiliser les fichiers locaux
    html_local = html_content
    for key, local_path in screenshots.items():
        if local_path and os.path.exists(local_path):
            filename = os.path.basename(local_path)
            old_url = f"https://audit.incidenx.com/{slug}/{filename}"
            if old_url in html_local:
                html_local = html_local.replace(old_url, filename)
    
    # Sauvegarder le HTML localement
    local_html_path = os.path.join(preview_dir, "index.html")
    with open(local_html_path, 'w', encoding='utf-8') as f:
        f.write(html_local)
    logger.error(f"[REPORTER] HTML sauvegardé localement: {local_html_path}")
    
    # URL locale pour prévisualisation
    local_url = f"local://{slug}/"
    
    if lead_id:
        try:
            from database.db_manager import get_conn
            with get_conn() as conn:
                desktop_path = screenshots.get("screenshot_desktop", "")
                mobile_path = screenshots.get("screenshot_mobile", "")
                conn.execute(
                    "UPDATE leads_audites SET rapport_html = ?, screenshot_desktop = ?, screenshot_mobile = ?, lien_rapport = ? WHERE lead_id = ?",
                    (html_content, desktop_path, mobile_path, local_url, lead_id)
                )
                conn.commit()
                logger.error(f"[REPORTER] Base mise à jour avec URL locale: {local_url}")
        except Exception as e:
            logger.warning(f"Impossible de sauvegarder HTML en base: {e}")
    
    # NOUVEAU WORKFLOW: Ne plus pousser automatiquement sur GitHub
    # L'utilisateur doit valider et pousser manuellement depuis le dashboard
    logger.error(f"[REPORTER] Rapport généré localement: {slug} (en attente de push)")
    
    # Nettoyer les anciens fichiers après génération réussie
    if os.path.exists(preview_dir) and os.path.exists(local_html_path):
        # Garder seulement les fichiers utilisés par le nouveau rapport
        used_files = set()
        for key, local_path in screenshots.items():
            if local_path and os.path.exists(local_path):
                used_files.add(os.path.basename(local_path))
        used_files.add('index.html')
        
        for f in os.listdir(preview_dir):
            if f not in used_files:
                try:
                    os.remove(os.path.join(preview_dir, f))
                except:
                    pass
    
    return local_url


# --- GÉNÉRATION PDF ---
async def capture_screenshot(url: str, output_path: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 1280, 'height': 720})
        try:
            await page.goto(url, timeout=30000, wait_until="networkidle")
            await page.screenshot(path=output_path)
            return True
        except: return False
        finally: await browser.close()

async def generate_pdf(audit_data: Dict[str, Any], output_pdf_path: str):
    enriched = enrich_data(audit_data)
    template_dir = os.path.join(os.path.dirname(__file__), "templates")
    env = Environment(loader=FileSystemLoader(template_dir))
    
    # Choix du template selon le profil
    template_name = "reputation_template.html" if audit_data.get("template_used") == "reputation" else "audit_template.html"
    template = env.get_template(template_name)
    
    # Screenshot
    img_tag = ""
    if enriched["has_site"]:
        site_url = audit_data.get("site_web")
        screenshot_path = os.path.join(os.path.dirname(__file__), "reports", "temp_site.png")
        os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
        if await capture_screenshot(site_url, screenshot_path):
            with open(screenshot_path, "rb") as f:
                img_tag = f"data:image/png;base64,{base64.b64encode(f.read()).decode('utf-8')}"
            if os.path.exists(screenshot_path): os.remove(screenshot_path)
    
    enriched["screenshot_path"] = img_tag
    html_content = template.render(**enriched)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(html_content)
        await asyncio.sleep(1)
        await page.pdf(path=output_pdf_path, format="A4", print_background=True)
        await browser.close()
    return True

async def main_execute(limit=None):
    sheet = get_sheet("Leads")
    all_rows = sheet.get_all_values()
    if not all_rows: return
    headers = all_rows[0]
    processed = 0
    for i, row in enumerate(all_rows[1:]):
        row_num = i + 2
        data = dict(zip(headers, row))
        if data.get("Service Proposé") and not data.get("Lien Rapport PDF"):
            print(f"   [Agent Reporter] Génération PDF pour {data.get('Nom')}...")
            try: full_data = json.loads(data.get("JSON Complet", "{}"))
            except: full_data = data
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            pdf_filename = f"Audit_{data.get('Nom').replace(' ', '_')}_{timestamp}.pdf"
            pdf_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "reports", pdf_filename))
            os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
            
            # Détection Profil A (sans site)
            has_site = full_data.get("site_web") not in [None, "", "sans_site", "SANS SITE"]
            
            if not has_site:
                print(f"   [Agent Reporter] 🎨 Profil A (sans site) : Génération de la Maquette...")
                from synthetiseur.mockup_generator import generate_mockup
                
                if 'id' not in full_data: full_data['id'] = row_num
                full_data['nom'] = full_data.get('nom') or data.get('Nom', '')
                full_data['ville'] = full_data.get('ville') or data.get('Ville', '')
                full_data['category'] = full_data.get('category') or data.get('Mot Cible', data.get('Catégorie', ''))
                
                mockup = generate_mockup(full_data)
                if mockup["success"]:
                    print(f"   [OK] Maquette générée")
                    # Sauvegarder les chemins en base
                    if full_data.get('id'):
                        try:
                            from database.db_manager import get_conn
                            with get_conn() as db_conn:
                                db_conn.execute("""
                                    UPDATE leads_audites 
                                    SET screenshot_desktop = ?, screenshot_mobile = ?
                                    WHERE lead_id = ?
                                """, (mockup.get("screenshot_desktop", ""), mockup.get("screenshot_mobile", ""), full_data.get('id')))
                                db_conn.commit()
                        except Exception as e:
                            logger.warning(f"Impossible de sauvegarder screenshots: {e}")
                else:
                    print(f"   [ERREUR] Échec de la maquette: {mockup.get('erreur')}")
            else:
                print(f"   [Agent Reporter] Rapport HTML publié (PDF désactivé)")
                
            processed += 1
            if limit and processed >= limit: break

# --- REPUBLICATION DEPUIS HTML STOCKE ---
def republish_from_db(lead_id: int = None, nom: str = None) -> str:
    """
    Republie un rapport en regenerant le HTML avec les vraies donnees.
    """
    from database.db_manager import get_conn
    conn = get_conn()
    
    if lead_id:
        audit_row = conn.execute(
            "SELECT * FROM leads_audites WHERE lead_id = ?",
            (lead_id,)
        ).fetchone()
        lead_row = conn.execute(
            "SELECT * FROM leads_bruts WHERE id = ?",
            (lead_id,)
        ).fetchone()
    elif nom:
        audit_row = conn.execute(
            "SELECT a.* FROM leads_audites a JOIN leads_bruts l ON a.lead_id = l.id WHERE l.nom LIKE ?",
            (f"%{nom}%",)
        ).fetchone()
        if audit_row:
            lead_row = conn.execute(
                "SELECT * FROM leads_bruts WHERE id = ?",
                (audit_row[1],)  # lead_id is second column
            ).fetchone()
        else:
            lead_row = None
    else:
        print("[ERREUR] lead_id ou nom requis")
        return None
    
    if not audit_row or not lead_row:
        print(f"[ERREUR] Prospect non trouve")
        return None
    
    # Get column names (PRAGMA returns: cid, name, type, notnull, dflt_value, pk)
    audit_cols = [desc[1] for desc in conn.execute('PRAGMA table_info(leads_audites)').fetchall()]
    lead_cols = [desc[1] for desc in conn.execute('PRAGMA table_info(leads_bruts)').fetchall()]
    
    # Merge audit + lead data
    audit_data = dict(zip(audit_cols, audit_row))
    lead_data = dict(zip(lead_cols, lead_row))
    
    # Merge (audit overrides lead)
    combined = {**lead_data, **audit_data}
    
    # Enrich and generate
    enriched = enrich_data(combined)
    
    # Select template
    template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates', 'rapports')
    env = Environment(loader=FileSystemLoader(template_dir))
    
    from synthetiseur.github_publisher import push_audit_to_github, generate_slug
    slug = generate_slug(combined.get("nom", "prospect"))
    
    template_used = combined.get("template_used", "audit")
    
    if template_used == "maquette" or not combined.get("site_web"):
        template = env.get_template("rapport-profil-a-maquette.html")
    elif template_used == "reputation" or combined.get("profil") == "C":
        template = env.get_template("rapport-profil-c-gmb.html")
    elif template_used == "seo":
        template = env.get_template("rapport-profil-b-technique.html")
    else:
        template = env.get_template("rapport-profil-b-technique.html")
    
    # Screenshots pour maquette (depuis base)
    screenshots = {}
    if template_used == "maquette" or not combined.get("site_web"):
        desktop_path = audit_data.get("screenshot_desktop", "")
        mobile_path = audit_data.get("screenshot_mobile", "")
        if desktop_path and os.path.exists(desktop_path):
            screenshots["screenshot_desktop"] = desktop_path
            enriched["screenshot_desktop"] = f"https://audit.incidenx.com/{slug}/{os.path.basename(desktop_path)}"
        if mobile_path and os.path.exists(mobile_path):
            screenshots["screenshot_mobile"] = mobile_path
            enriched["screenshot_mobile"] = f"https://audit.incidenx.com/{slug}/{os.path.basename(mobile_path)}"
    
    html_content = template.render(**enriched)
    
    # Publish
    public_url, _ = push_audit_to_github(slug, html_content, screenshots)
    
    print(f"[OK] Republie: {public_url}")
    return public_url

def verify_and_republish(lead_id: int = None, nom: str = None) -> str:
    """
    Verifie si le lien est accessible, sinon republie depuis le HTML stocke.
    """
    import requests
    from database.db_manager import get_conn
    conn = get_conn()
    
    if lead_id:
        row = conn.execute("SELECT lead_id, lien_rapport, rapport_html FROM leads_audites WHERE lead_id = ?", (lead_id,)).fetchone()
    elif nom:
        row = conn.execute(
            "SELECT la.lead_id, la.lien_rapport, la.rapport_html FROM leads_audites la JOIN leads_bruts l ON la.lead_id = l.id WHERE l.nom LIKE ?",
            (f"%{nom}%",)
        ).fetchone()
    else:
        print("[ERREUR] lead_id ou nom requis")
        return None
    
    if not row:
        print(f"[ERREUR] Prospect non trouve")
        return None
    
    lead_id, lien_rapport, rapport_html = row
    
    if not lien_rapport:
        print(f"[ATTENTION] Pas de lien stocke pour ID {lead_id}")
        return republish_from_db(lead_id=lead_id) if rapport_html else None
    
    try:
        response = requests.head(lien_rapport, timeout=10, allow_redirects=True)
        if response.status_code == 200:
            print(f"[OK] Lien accessible: {lien_rapport}")
            return lien_rapport
        else:
            print(f"[ATTENTION] Lien inaccessible ({response.status_code}): {lien_rapport}")
    except Exception as e:
        print(f"[ATTENTION] Erreur verification: {e}")
    
    if rapport_html:
        print(f"Republication depuis HTML stocke...")
        return republish_from_db(lead_id=lead_id)
    else:
        print(f"[ERREUR] Aucun HTML stocke pour republier")
        return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(main_execute(args.limit))
