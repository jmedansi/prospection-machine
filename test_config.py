"""
Script test_config.py
Affiche la config active et vérifie la connexion au Google Sheets.
"""
import logging
from config_manager import get_config, check_limits

# Logger
logging.basicConfig(
    filename='errors.log',
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def test():
    """Test global de la configuration."""
    print("Démarrage du test de configuration Google Sheets...\n")
    try:
        config = get_config()
        if not config:
            print("Erreur: Impossible de lire la configuration active ou aucun compte ACTIF.")
            return
            
        print("La configuration active a bien été récupérée :")
        for key, val in config.items():
            # Masquer partiellement les clés (protection)
            if "key" in key and isinstance(val, str) and len(val) > 8:
                display_val = val[:4] + "***" + val[-4:]
            else:
                display_val = val
            print(f" - {key}: {display_val}")
            
        print("\nVérification des limites via check_limits() :")
        alertes = check_limits()
        if alertes:
            for alerte in alertes:
                print(alerte)
        else:
            print("Toutes les limites d'utilisation sont correctes.")
            
        print("\n✅ Config OK")
    
    except Exception as e:
        logging.error(f"Erreur lors du test de la config: {e}")
        print(f"Une erreur est survenue lors du test: {e}")

if __name__ == "__main__":
    test()
