"""
Module gemini_maps.py
Recherche géolocalisée via l'outil natif Google Maps de Gemini, renvoyant un JSON structuré.
"""
import logging
import json
from google import genai
from google.genai.types import GoogleMaps, Tool, GenerateContentConfig
from config_manager import get_config

logging.basicConfig(
    filename='errors.log',
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def search_local_businesses(query: str) -> str:
    """Ancienne fonction de test."""
    pass

def get_places_json(keyword: str, city: str) -> list:
    """
    Lance une recherche via Gemini 2.5 Flash avec l'outil Google Maps
    et retourne un tableau JSON strict contenant les informations demandées pour chaque lieu.
    """
    try:
        config = get_config()
        if not config:
            raise ValueError("Configuration non trouvée. Veuillez vérifier Google Sheets et lancer config_manager.py.")
            
        api_key = config.get('google_api_key')
        if not api_key:
            raise ValueError("Clé google_api_key manquante dans la configuration active.")
            
        client = genai.Client(api_key=api_key)
        
        prompt = f"""
        Fais une recherche d'établissements pour le mot-clé '{keyword}' à '{city}' en utilisant Google Maps.
        Tu dois extraire les 20 premiers résultats pertinents.
        
        ATTENTION: Tu dois retourner UNIQUEMENT un tableau JSON strict et valide.
        Ne mets AUCUN texte avant ou après le JSON. Ne mets pas de bloc ```json.
        
        Le format de chaque objet du tableau doit être exactement celui-ci:
        {{
            "nom": "Nom de l'établissement",
            "adresse": "Adresse complète",
            "site_web": "Site web officiel (Ne mets JAMAIS un lien vers Google Maps, Facebook, Instagram ou un annuaire. Si pas de vrai site web personnel, mets null)",
            "telephone": "Numéro de téléphone",
            "rating": 4.5,
            "nb_avis": 128,
            "email": "Email public de l'établissement s'il est connu (y compris gmail, yahoo, etc). Sinon null"
        }}
        
        Si une information est introuvable, mets null (sans guillemets).
        """
        
        print(f"Recherche Gemini Maps en cours (Google Places contourné) pour '{keyword} {city}'...")
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=GenerateContentConfig(
                tools=[Tool(google_maps=GoogleMaps())],
                temperature=0.0
            ),
        )
        
        # Nettoyage de la réponse pour parser le JSON si Gemini a quand même mis des formateurs markdown
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
            
        if text.endswith("```"):
            text = text[:-3]
            
        return json.loads(text.strip())
        
    except json.JSONDecodeError as e:
        error_msg = f"Erreur de parsage JSON Gemini: {e}\nRéponse brute: {response.text}"
        logging.error(error_msg)
        return []
        
    except Exception as e:
        error_msg = f"Erreur lors de la recherche Gemini Maps: {e}"
        logging.error(error_msg)
        return []

if __name__ == "__main__":
    print("Démarrage du test Gemini Maps structuré...")
    resultats = get_places_json("restaurant", "Cotonou")
    print(f"\n{len(resultats)} résultats trouvés.")
    for r in resultats[:3]:
        print(f"- {r.get('nom')} / {r.get('site_web')} / Rating: {r.get('rating')} ({r.get('nb_avis')} avis)")
