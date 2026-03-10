"""
Script setup_sheets.py
Initialise les feuilles nécessaires dans le doc Google Sheets, avec les bons en-têtes.
Ajoute aussi une ligne d'exemple dans config_comptes.
"""
import os
import logging
from config_manager import get_client

# Toujours logger les erreurs
logging.basicConfig(
    filename='errors.log',
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def setup():
    """Crée les en-têtes de sheets et les onglets par défaut."""
    try:
        sheet_id = os.getenv("GOOGLE_SHEETS_ID")
        if not sheet_id:
            print("Erreur: GOOGLE_SHEETS_ID non défini dans .env")
            return
            
        client = get_client()
        spreadsheet = client.open_by_key(sheet_id)
        
        # Définition des feuilles et en-têtes
        sheets_def = {
            "leads_bruts": ["Date de scraping", "Mot-clé", "Nom du restaurant", "Adresse", "Téléphone", "Site web", "Note", "Avis", "Email de contact", "Statut Email", "Service proposé", "Mail à envoyer"],
            "leads_audites": ["Date", "Nom", "Entreprise", "Email_trouvé", "Score", "Statut"],
            "emails_envoyes": ["Date", "Email", "Sujet", "Statut d'envoi", "Ouverture"],
            "config_comptes": [
                "compte_id", "actif", "hunter_key", "carbone_key", "brevo_key",
                "google_api_key", "anthropic_key", "hunter_usage", "carbone_usage",
                "brevo_usage", "date_reset"
            ]
        }
        
        for name, headers in sheets_def.items():
            try:
                worksheet = spreadsheet.worksheet(name)
                print(f"La feuille '{name}' existe déjà.")
            except Exception:
                # La worksheet n'existe pas, on la crée
                worksheet = spreadsheet.add_worksheet(title=name, rows=100, cols=20)
                print(f"Feuille '{name}' créée avec succès.")
            
            # Mise à jour des en-têtes (Ligne 1) pour s'assurer qu'ils sont corrects
            # On met à jour la ligne 1, colonnes correspondant au nb de headers
            cell_range = f"A1:{chr(64 + len(headers))}1"
            worksheet.update([headers], cell_range)
            print(f"En-têtes mis à jour pour '{name}'.")
            
            # Si c'est config_comptes et qu'il n'y a pas de donnée, on injecte un exemple
            if name == "config_comptes":
                records = worksheet.get_all_records()
                if not records:
                    example_row = [
                        "compte_1", "TRUE", "hunter_test_key", "carbone_test_key", "brevo_test_key",
                        "google_test_key", "anthropic_test_key", 0, 0, 0, "2026-04-01"
                    ]
                    worksheet.append_row(example_row)
                    print("Ligne exemple ajoutée à 'config_comptes'.")
                    
        print("\nSetup des Google Sheets complété avec succès !")

    except Exception as e:
        import traceback
        logging.error(f"Erreur dans setup_sheets: {traceback.format_exc()}")
        print(f"Erreur lors du setup:\n{traceback.format_exc()}")

if __name__ == "__main__":
    setup()
