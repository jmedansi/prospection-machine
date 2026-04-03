# -*- coding: utf-8 -*-
import requests
import re
import logging
import os
from bs4 import BeautifulSoup
from typing import Dict, Any
from config_manager import get_active_client

logger = logging.getLogger(__name__)

def run_pagespeed(url: str, strategy: str = "mobile") -> Dict[str, Any]:
    """
    ÉTAPE 2 — PageSpeed Insights API (Mobile ou Desktop).
    Retourne None pour les scores si l'API échoue ou retourne des données invalides.
    """
    try:
        api_key = None
        try:
            client = get_active_client()
            api_key = client.get("google_api_key")
        except:
            pass
            
        psi_url = f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url={url}&strategy={strategy}"
        if api_key:
            psi_url += f"&key={api_key}"
            
        resp = requests.get(psi_url, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        
        lh = data.get('lighthouseResult', {})
        audits = lh.get('audits', {})
        categories = lh.get('categories', {})
        
        prefix = "mobile" if strategy == "mobile" else "desktop"
        
        performance_score = categories.get('performance', {}).get('score')
        
        if performance_score is None:
            logger.warning(f"PageSpeed: score manquant pour {url} ({strategy})")
            return {f"{prefix}_score": None, f"{prefix}_lcp_ms": None}
        
        score = performance_score * 100
        
        lcp = audits.get('largest-contentful-paint', {}).get('numericValue')
        if lcp is not None and lcp > 60000:
            lcp = None
            
        return {
            f"{prefix}_score": score,
            f"{prefix}_lcp_ms": lcp,
            "fcp_ms": audits.get('first-contentful-paint', {}).get('numericValue'),
            "cls": audits.get('cumulative-layout-shift', {}).get('numericValue'),
            "page_size_kb": audits.get('total-byte-weight', {}).get('numericValue', 0) / 1024,
            "render_blocking_scripts": len(audits.get('render-blocking-resources', {}).get('details', {}).get('items', [])),
            "uses_cache": audits.get('uses-long-cache-ttl', {}).get('score', 0) == 1
        }
    except Exception as e:
        logger.error(f"Erreur PageSpeed ({strategy}) pour {url}: {e}")
        return {f"{prefix}_score": None, f"{prefix}_lcp_ms": None}

def parse_html(url: str) -> Dict[str, Any]:
    """
    ÉTAPE 3 — BeautifulSoup parsing (Zéro LLM).
    Retourne None pour les champs SEO si l'analyse échoue.
    """
    data = {
        "has_title": False, "title_length": 0, "has_meta_description": None,
        "h1_count": 0, "has_contact_button": False, "visible_text_words": 0,
        "has_schema": None, "has_robots": None, "has_sitemap": None,
        "has_responsive_meta": False, "has_https": url.startswith("https://"),
        "tel_link": False, "images_count": 0, "images_without_alt": 0,
        "has_analytics": False, "cms_detected": None, "has_google_fonts": False
    }
    try:
        resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        if soup.title:
            data["has_title"] = True
            data["title_length"] = len(soup.title.string or "")
        
        # SEO & Structure
        if soup.find('meta', attrs={'name': 'description'}):
            data["has_meta_description"] = True
        else:
            data["has_meta_description"] = False
            
        data["h1_count"] = len(soup.find_all('h1'))
        
        contact_tags = soup.find_all(['a', 'button'], href=re.compile(r'tel:|contact', re.I))
        data["has_contact_button"] = len(contact_tags) > 0
        
        # Ratio texte/HTML
        visible_text = soup.get_text()
        data["visible_text_words"] = len(visible_text.split())
        html_content = resp.text
        if len(html_content) > 0:
            data["text_to_html_ratio"] = (len(visible_text) / len(html_content)) * 100
        else:
            data["text_to_html_ratio"] = 0
        
        scripts = soup.find_all('script', type='application/ld+json')
        data["has_schema"] = any('LocalBusiness' in (s.string or "") for s in scripts)
        
        # Vérification fichiers SEO standard (robots.txt, sitemap)
        base_url = "/".join(url.split("/")[:3])
        try:
            data["has_robots"] = requests.get(f"{base_url}/robots.txt", timeout=5).status_code == 200
            data["has_sitemap"] = requests.get(f"{base_url}/sitemap.xml", timeout=5).status_code == 200
        except:
            pass
        
        # Meta viewport
        if soup.find('meta', attrs={'name': 'viewport'}):
            data["has_responsive_meta"] = True
            
        # Nouveaux ajouts parse_html
        data["tel_link"] = bool(soup.find("a", href=lambda h: h and "tel:" in h))
        data["images_count"] = len(soup.find_all("img"))
        data["images_without_alt"] = len([i for i in soup.find_all("img") if not i.get("alt")])
        data["has_analytics"] = bool(re.search(r'gtag|ga\.js|fbq|pixel', str(soup), re.I))
        data["cms_detected"] = next((cms for cms in ["wp-content","wix.com","jimdo","squarespace","weebly"] 
                                   if cms in str(soup)), None)
        if data["cms_detected"] == "wp-content": 
            data["cms_detected"] = "wordpress"
        elif isinstance(data["cms_detected"], str): 
            data["cms_detected"] = data["cms_detected"].replace(".com", "")
        
        data["has_google_fonts"] = "fonts.googleapis.com" in str(soup)
        
        return data
    except Exception as e:
        logger.error(f"Erreur parse_html: {e}")
        return data

def run_web_analysis(url: str, report_dir: str = None) -> Dict[str, Any]:
    """Orchestration de l'analyse web technique (Mobile + Desktop)."""
    print(f"   [Agent Web] Analyse technique complète de {url}...")
    
    # 1. PageSpeed Mobile
    mobile_data = run_pagespeed(url, strategy="mobile")
    
    # 2. PageSpeed Desktop
    desktop_data = run_pagespeed(url, strategy="desktop")
    
    # 3. Parsing HTML
    html_data = parse_html(url)
    
    # Fusion des résultats
    all_results = {**mobile_data, **desktop_data, **html_data}
    
    # Calcul score tablette (Moyenne mobile/desktop) - seulement si les deux scores existent
    m_score = all_results.get("mobile_score")
    d_score = all_results.get("desktop_score")
    
    if m_score is not None and d_score is not None:
        all_results["tablet_score"] = int((m_score + d_score) / 2)
    elif m_score is not None:
        all_results["tablet_score"] = m_score
    elif d_score is not None:
        all_results["tablet_score"] = d_score
    else:
        all_results["tablet_score"] = None
    
    # Pour compatibilité descendante
    all_results["lcp_ms"] = all_results.get("mobile_lcp_ms")
    all_results["site_analysee"] = url
    
    # Nouveau : Screenshot si report_dir est fourni
    if report_dir:
        from utils.screenshot_helper import capture_site_mobile
        shot_path = os.path.join(report_dir, "preview.png")
        if capture_site_mobile(url, shot_path):
            all_results["screenshot_path"] = "preview.png"
    
    return all_results
