"""
Module config_manager.py
Gère la lecture des clés API depuis Google Sheets et les limites d'utilisation.
"""
import os
import logging
from typing import Dict, List, Any
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

# Configuration du logger pour enregistrer les erreurs dans errors.log
logging.basicConfig(
    filename='errors.log',
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Chargement des variables d'environnement depuis le fichier .env
load_dotenv()

# Les scopes nécessaires pour lire et écrire dans Google Sheets
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

def get_client() -> gspread.client.Client:
    """
    Initialise et retourne le client authentifié pour Google Sheets.
    Gère les erreurs et les logs dans errors.log.
    """
    try:
        credentials_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        if not credentials_file:
            raise ValueError("La variable GOOGLE_SERVICE_ACCOUNT_JSON est manquante dans .env")
        
        credentials = Credentials.from_service_account_file(credentials_file, scopes=SCOPES)
        client = gspread.authorize(credentials)
        return client
    except Exception as e:
        logging.error(f"Erreur d'authentification Google Sheets: {e}")
        raise

def get_sheet(sheet_name: str) -> gspread.worksheet.Worksheet:
    """
    Récupère une feuille de calcul par son nom.
    """
    try:
        sheet_id = os.getenv("GOOGLE_SHEETS_ID")
        if not sheet_id:
            raise ValueError("La variable GOOGLE_SHEETS_ID est manquante dans .env")
        
        client = get_client()
        sheet = client.open_by_key(sheet_id).worksheet(sheet_name)
        return sheet
    except Exception as e:
        logging.error(f"Erreur lors de l'accès à la feuille {sheet_name}: {e}")
        raise

def get_config() -> Dict[str, Any]:
    """
    Retourne un dictionnaire avec toutes les clés actives du document 'config_comptes'.
    On cherche la ligne ayant la colonne 'actif' à TRUE.
    """
    try:
        sheet = get_sheet("config_comptes")
        records = sheet.get_all_records()
        for row in records:
            # On vérifie si le compte est actif (TRUE)
            if str(row.get('actif', '')).strip().upper() == 'TRUE':
                return dict(row)
        return {}
    except Exception as e:
        logging.error(f"Erreur dans get_config: {e}")
        return {}

def increment_usage(service: str) -> None:
    """
    Incrémente le compteur du service passé en paramètre (hunter, carbone, brevo)
    pour le compte actif.
    """
    try:
        sheet = get_sheet("config_comptes")
        records = sheet.get_all_records()
        col_usage = f"{service}_usage"
        
        # On parcourt les lignes (la ligne 1 est l'en-tête, la 2 est le 1er enregistrement)
        for i, row in enumerate(records, start=2):
            if str(row.get('actif', '')).strip().upper() == 'TRUE':
                current_value = row.get(col_usage, 0)
                try:
                    current_value = int(current_value) if current_value else 0
                except ValueError:
                    current_value = 0
                
                # Mise à jour de la cellule
                cell = sheet.find(col_usage, in_row=1)
                sheet.update_cell(i, cell.col, current_value + 1)
                break
    except Exception as e:
        logging.error(f"Erreur dans increment_usage ({service}): {e}")

def check_limits() -> List[str]:
    """
    Retourne une liste de warnings si les compteurs sont proches de la limite.
    (hunter >= 23, carbone >= 90, brevo >= 280).
    """
    warnings = []
    try:
        config = get_config()
        if not config:
            return ["Aucune config active pour vérifier les limites."]
        
        # Récupération sécurisée des compteurs
        hunter = int(config.get('hunter_usage', 0) or 0)
        carbone = int(config.get('carbone_usage', 0) or 0)
        brevo = int(config.get('brevo_usage', 0) or 0)
        
        if hunter >= 23:
            warnings.append(f"ALERTE Hunter: {hunter}/25 requêtes utilisées.")
        if carbone >= 90:
            warnings.append(f"ALERTE Carbone/Dropcontact: {carbone}/100 requêtes utilisées.")
        if brevo >= 280:
            warnings.append(f"ALERTE Brevo: {brevo}/300 emails envoyés.")
    
    except Exception as e:
        logging.error(f"Erreur dans check_limits: {e}")
    
    return warnings

def get_status() -> List[Dict[str, Any]]:
    """
    Retourne l'état de tous les comptes pour un dashboard futur.
    """
    try:
        sheet = get_sheet("config_comptes")
        return sheet.get_all_records()
    except Exception as e:
        logging.error(f"Erreur dans get_status: {e}")
        return []
