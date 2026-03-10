"""
Script fix_sheets.py
Ce script va vider l'onglet 'leads_bruts' qui contient les mauvais alignements de colonnes des tests précédents,
puis y réécrire uniquement les nouveaux en-têtes proprement alignés.
"""
import os
import logging
from config_manager import get_client

def fix():
    logging.basicConfig(filename='errors.log', level=logging.ERROR)
    try:
        sheet_id = os.getenv("GOOGLE_SHEETS_ID")
        client = get_client()
        spreadsheet = client.open_by_key(sheet_id)
        
        # Ouvre leads_bruts
        worksheet = spreadsheet.worksheet("leads_bruts")
        
        print("Nettoyage de l'onglet 'leads_bruts'...")
        worksheet.clear()
        
        headers = ["Date de scraping", "Mot-clé", "Nom du restaurant", "Adresse", "Téléphone", "Site web", "Note", "Avis", "Email de contact", "Statut Email", "Service proposé", "Mail à envoyer"]
        cell_range = f"A1:{chr(64 + len(headers))}1"
        worksheet.update([headers], cell_range)
        print("L'onglet a été nettoyé et les nouveaux en-têtes ont été appliqués avec succès.")
        
    except Exception as e:
        print(f"Erreur lors de la réparation: {e}")

if __name__ == "__main__":
    fix()
