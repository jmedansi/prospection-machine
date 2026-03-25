# -*- coding: utf-8 -*-
"""
Module config_manager.py — v2
Gère la rotation automatique de providers LLM (Gemini × 5 + Groq × 5).
Lit la configuration depuis Google Sheets (feuille "config_comptes").
Fournit un point d'entrée unique handle_llm_call() pour tous les agents.
"""
import os
import time
import logging
import requests
from datetime import date, datetime
from typing import Dict, Any, List, Optional

from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

# Chargement du .env
load_dotenv()

# --- Logging ---
logging.basicConfig(
    filename='errors.log',
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Constantes ---
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

CACHE_TTL = 300  # 5 minutes

# Cache interne (évite des appels répétitifs à Sheets)
_cache: Dict[str, Any] = {
    "active_client": None,
    "cache_ts": 0.0,
    "all_records": None,
    "records_ts": 0.0,
    "gspread_client": None,
    "spreadsheet": None,
    "worksheets": {} # Cache pour les objets worksheet
}


# ===========================================================
# HELPERS SHEETS
# ===========================================================

def _get_gspread_client() -> gspread.client.Client:
    """Retourne le client gspread authentifié (avec cache)."""
    if _cache["gspread_client"]:
        return _cache["gspread_client"]
    try:
        credentials_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        if not credentials_file:
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON manquant dans .env")
        creds = Credentials.from_service_account_file(credentials_file, scopes=SCOPES)
        _cache["gspread_client"] = gspread.authorize(creds)
        return _cache["gspread_client"]
    except Exception as e:
        logger.error(f"Erreur authentification gspread: {e}")
        raise


def get_sheet(sheet_name: str) -> gspread.worksheet.Worksheet:
    """Récupère une feuille par son nom (avec cache)."""
    if sheet_name in _cache["worksheets"]:
        return _cache["worksheets"][sheet_name]
    try:
        sheet_id = os.getenv("GOOGLE_SHEETS_ID")
        if not sheet_id:
            raise ValueError("GOOGLE_SHEETS_ID manquant dans .env")
        
        if not _cache["spreadsheet"]:
            client = _get_gspread_client()
            _cache["spreadsheet"] = client.open_by_key(sheet_id)
            
        sheet = _cache["spreadsheet"].worksheet(sheet_name)
        _cache["worksheets"][sheet_name] = sheet
        return sheet
    except Exception as e:
        logger.error(f"Erreur accès feuille {sheet_name}: {e}")
        raise


def _get_all_records(force: bool = False) -> List[Dict[str, Any]]:
    """
    Lit tous les comptes de config_comptes avec cache 5 min.
    Force=True vide le cache avant lecture.
    """
    now = time.time()
    if force or (now - _cache["records_ts"]) > CACHE_TTL or _cache["all_records"] is None:
        sheet = get_sheet("config_comptes")
        expected_headers = [
            "compte_id", "actif", "groq_key", "google_api_key", "hunter_key", "brevo_key",
            "outscraper_key", "hunter_usage", "brevo_usage", "date_reset"
        ]
        try:
            _cache["all_records"] = sheet.get_all_records(expected_headers=expected_headers)
        except Exception:
            _cache["all_records"] = sheet.get_all_records()
            
        _cache["records_ts"] = now
    return _cache["all_records"]


def _get_row_index(compte_id: str) -> int:
    """Retourne le numéro de ligne (1-indexed, en tenant compte de l'en-tête)."""
    records = _get_all_records(force=True)
    for i, row in enumerate(records, start=2):  # ligne 2 = première donnée
        if str(row.get("compte_id")) == str(compte_id):
            return i
    raise ValueError(f"compte_id {compte_id} introuvable dans config_comptes")


def _update_cell(compte_id: str, col_name: str, value: Any) -> None:
    """Met à jour une cellule spécifique pour un compte."""
    try:
        sheet = get_sheet("config_comptes")
        row_idx = _get_row_index(compte_id)
        # Trouver la colonne par son nom
        header_row = sheet.row_values(1)
        if col_name not in header_row:
            raise ValueError(f"Colonne '{col_name}' introuvable dans config_comptes")
        col_idx = header_row.index(col_name) + 1
        sheet.update_cell(row_idx, col_idx, value)
    except Exception as e:
        logger.error(f"Erreur _update_cell({compte_id}, {col_name}): {e}")
        raise


# ===========================================================
# RESET QUOTIDIEN
# ===========================================================

def check_daily_reset() -> None:
    """
    Appelée au démarrage de chaque agent.
    Remet à zéro les usages si date_reset < aujourd'hui.
    """
    try:
        records = _get_all_records(force=True)
        today_str = date.today().isoformat()

        for row in records:
            reset_date = str(row.get("date_reset", "")).strip()
            compte_id = row.get("compte_id")

            if reset_date and reset_date < today_str:
                _update_cell(compte_id, "hunter_usage", 0)
                _update_cell(compte_id, "carbone_usage", 0)
                _update_cell(compte_id, "brevo_usage", 0)
                _update_cell(compte_id, "date_reset", today_str)
                logger.info(f"Compte {compte_id} remis à zéro (reset journalier).")

        # Vider le cache après reset
        _cache["all_records"] = None
    except Exception as e:
        logger.error(f"Erreur check_daily_reset: {e}")


# ===========================================================
# GESTION DES COMPTES
# ===========================================================

def get_active_client() -> Dict[str, Any]:
    """
    Retourne le compte actif (actif=TRUE) avec provider, model, api_key.
    Cache 5 minutes pour éviter trop d'appels Sheets.
    """
    now = time.time()
    if _cache["active_client"] and (now - _cache["cache_ts"]) < CACHE_TTL:
        return _cache["active_client"]

    try:
        records = _get_all_records(force=True)
        for row in records:
            if str(row.get("actif", "")).strip().upper() == "TRUE":
                _cache["active_client"] = dict(row)
                _cache["cache_ts"] = now
                return _cache["active_client"]

        raise ValueError("Aucun compte actif (actif=TRUE) trouvé dans config_comptes.")
    except Exception as e:
        logger.error(f"Erreur get_active_client: {e}")
        raise


def get_llm_client(client_info: Optional[Dict[str, Any]] = None):
    """
    Retourne le client LLM Groq (seul provider utilisé).
    """
    if client_info is None:
        client_info = get_active_client()

    groq_key = client_info.get("groq_key") or client_info.get("GROQ_API_KEY")
    if groq_key:
        from openai import OpenAI
        return OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=groq_key
        )

    raise ValueError("Aucune clé API Groq (groq_key) trouvée dans config_comptes.")


def switch_to_next(reason: str = "") -> Dict[str, Any]:
    """
    Bascule vers le compte suivant disponible.
    (Simple bascule entre lignes où actif=TRUE)
    """
    try:
        # On désactive l'actuel
        try:
            current = get_active_client()
            _update_cell(current["compte_id"], "actif", "FALSE")
        except:
            pass

        records = _get_all_records(force=True)
        for row in records:
            if str(row.get("actif", "")).strip().upper() == "FALSE":
                _update_cell(row["compte_id"], "actif", "TRUE")
                _cache["active_client"] = None
                return dict(row)

        raise AllQuotasExhausted("Plus aucun compte disponible.")
    except Exception as e:
        logger.error(f"Erreur switch_to_next: {e}")
        raise


# mark_quota_exhausted() supprimé — code mort


def increment_usage(compte_id: str, service: str = "hunter") -> None:
    """Incrémente l'usage pour un service spécifique (hunter, carbone, brevo)."""
    try:
        col_name = f"{service}_usage"
        records = _get_all_records(force=True)
        for row in records:
            if str(row.get("compte_id")) == str(compte_id):
                current = int(row.get(col_name, 0) or 0)
                _update_cell(compte_id, col_name, current + 1)
                _cache["all_records"] = None
                return
    except Exception as e:
        logger.error(f"Erreur increment_usage({compte_id}, {service}): {e}")


# ===========================================================
# POINT D'ENTRÉE UNIQUE — handle_llm_call()
# ===========================================================

MAX_RETRIES = 10  # 10 comptes au total

def handle_llm_call(prompt: str, system: str = "Tu es un consultant business expert.", provider: str = None, model: Optional[str] = None) -> str:
    """
    Point d'entrée unique — utilise exclusivement Groq (LLaMA 3.3 70B).
    Plus de dépendance Gemini.
    """
    try:
        client_info = get_active_client()
        api_key = client_info.get("groq_key") or client_info.get("GROQ_API_KEY")

        if not api_key:
            raise ValueError("Aucune clé Groq (groq_key) trouvée dans config_comptes.")

        from openai import OpenAI
        client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=api_key
        )
        response = client.chat.completions.create(
            model=model or "llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content

    except Exception as e:
        logger.error(f"Erreur handle_llm_call: {e}")
        raise


# ===========================================================
# RAPPORT DE STATUT
# ===========================================================

def get_status_report() -> Dict[str, Any]:
    """
    Retourne l'état simplifié de tous les comptes.
    """
    try:
        records = _get_all_records(force=True)
        
        compte_actuel = None
        for r in records:
            if str(r.get("actif", "")).strip().upper() == "TRUE":
                compte_actuel = r
                break

        return {
            "total_comptes": len(records),
            "compte_actuel_id": compte_actuel.get("compte_id") if compte_actuel else None,
            "comptes": records
        }
    except Exception as e:
        logger.error(f"Erreur get_status_report: {e}")
        return {"error": str(e)}


# ===========================================================
# ALERTE BREVO
# ===========================================================

def _send_alert_email(message: str) -> None:
    """Envoie une alerte email via Resend quand tous les quotas sont épuisés."""
    try:
        config = get_config()
        resend_key = config.get("resend_key")
        if not resend_key:
            logger.error("resend_key manquante, alerte non envoyée.")
            return

        url = "https://api.resend.com/emails"
        headers = {
            "Authorization": f"Bearer {resend_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "from": "ProspectionMachine <onboarding@resend.dev>",
            "to": ["jmedansi@incidenx.com"],
            "subject": "🚨 ALERTE — Tous les quotas LLM épuisés",
            "html": f"<p>{message}</p>"
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        logger.error(f"Alerte Resend envoyée : {message[:80]}")
    except Exception as e:
        logger.error(f"Erreur envoi alerte Resend: {e}")


# ===========================================================
# EXCEPTION PERSONNALISÉE
# ===========================================================

class AllQuotasExhausted(Exception):
    """Levée quand aucun compte LLM n'est disponible."""
    pass


# ===========================================================
# BACKWARD COMPATIBILITY — get_config()
# ===========================================================

def get_config() -> Dict[str, Any]:
    """
    Retourne le compte actif comme dict (compatibilité avec les anciens agents).
    Fusionne avec les clés de service (.env ou colonnes supplémentaires).
    """
    config = {}
    try:
        config = get_active_client()
    except Exception:
        # Fallback : lire toutes les lignes et retourner la première avec actif=TRUE
        try:
            sheet = get_sheet("config_comptes")
            records = sheet.get_all_records()
            for row in records:
                if str(row.get("actif", "")).strip().upper() == "TRUE":
                    config = dict(row)
                    break
        except Exception as e:
            logger.error(f"Erreur get_config fallback: {e}")
    
    # Fusionner avec les variables d'environnement (Brevo, Vercel, etc.)
    config["brevo_key"] = os.getenv("BREVO_API_KEY", config.get("brevo_key"))
    config["resend_key"] = os.getenv("RESEND_API_KEY")
    config["vercel_token"] = os.getenv("VERCEL_TOKEN")
    config["vercel_project_id"] = os.getenv("VERCEL_PROJECT_ID")
    config["vercel_org_id"] = os.getenv("VERCEL_ORG_ID")
    config["vercel_project_name"] = os.getenv("VERCEL_PROJECT_NAME", "incidenx-audit")
    config["audit_domain"] = os.getenv("AUDIT_DOMAIN", "audit.incidenx.com")
    # config["hunter_api_key"] = os.getenv("HUNTER_API_KEY", "") # Désactivé par l'utilisateur
    config["github_token"] = os.getenv("GITHUB_TOKEN", "")
    
    return config

if __name__ == "__main__":
    try:
        compte = get_active_client()
        print(f"✅ Config OK — Compte actif : {compte.get('compte_id')}")
    except Exception as e:
        print(f"❌ Erreur Config : {e}")
