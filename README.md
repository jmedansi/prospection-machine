# Module Config Manager & Sheets

Ce module gère la configuration des clés API et les quotas via Google Sheets.

## Installation
1. `pip install -r requirements.txt`
2. Copiez `.env.example` en `.env` et remplissez `GOOGLE_SHEETS_ID` et `GOOGLE_SERVICE_ACCOUNT_JSON`.
3. Lancez `python setup_sheets.py` pour initialiser le document Google Sheets.

## Test
Lancer `python test_config.py` pour vérifier la configuration active et l'état des limites.

## Module Gemini Maps
Un module `gemini_maps.py` est inclus pour effectuer des recherches de prospects géolocalisés (via l'outil natif Google Maps de Gemini).
Vous pouvez le tester avec : `python gemini_maps.py`. Il lira automatiquement `google_api_key` depuis vos configurations Sheets.
