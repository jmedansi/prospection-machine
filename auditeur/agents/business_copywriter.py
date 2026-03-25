# -*- coding: utf-8 -*-
"""
auditeur/agents/business_copywriter.py
Agent de relecture (Proofreader) pour emails de prospection.
Version V7 : Correction grammaticale uniquement.
"""
import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

PROOFREADER_PROMPT = """
Corrige uniquement les fautes d'orthographe, de grammaire et de ponctuation dans cet email.
Ne change pas le contenu, ne reformule pas les phrases, ne remplace pas les noms propres.
Garde les balises HTML intactes.
Retourne uniquement le HTML corrigé.
"""

def proofread_email_via_llm(html_content: str) -> str:
    """
    Utilise le LLM (Gemini Flash ou Llama) pour relire et corriger le HTML.
    """
    try:
        from config_manager import get_llm_client
        client = get_llm_client()
        
        # Le client utilisera le modèle configuré (Flash par défaut si disponible)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile", # Ou gemini-1.5-flash si configuré dans le client
            messages=[
                {"role": "system", "content": PROOFREADER_PROMPT},
                {"role": "user", "content": html_content}
            ],
            temperature=0.1 # On reste très strict
        )
        
        corrected_html = response.choices[0].message.content
        # Nettoyage si le LLM a ajouté des balises ```html
        corrected_html = corrected_html.replace("```html", "").replace("```", "").strip()
        return corrected_html
    except Exception as e:
        logger.error(f"Erreur Proofreading LLM: {e}")
        return html_content # Fallback sur l'original si erreur

def generate_email(lead_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fonction de compatibilité. Dans la V7, la génération se fait via email_builder.
    On retourne ici un dictionnaire vide ou minimal car build_premium_email fera le travail.
    """
    return {
        "email_objet": "Analyse de visibilité",
        "email_corps_texte": "",
        "proofread_required": True
    }