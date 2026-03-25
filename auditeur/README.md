# Agent Auditeur Web

Cet agent analyse le design, la performance et le SEO d'un site web pour calculer un score de priorité de prospection.

## Architecture
- **Orchestrateur** : Gemini 2.5 Flash avec Function Calling automatique.
- **Outils** :
  - `design_analyzer` : Playwright + BS4 (screenshots + analyse visuelle).
  - `performance_monitor` : Google PageSpeed Insights API.
  - `seo_crawler` : BS4 + Regex (balises meta, Schema.org, sitemaps).

## Installation
1. Installez les dépendances :
   ```bash
   pip install google-genai playwright beautifulsoup4 requests gspread python-dotenv
   playwright install chromium
   ```
2. Configurez votre `.env` (ou remplissez la feuille `config_comptes` dans Google Sheets).

## Utilisation
```bash
python auditeur/main.py
```

## Résultats
Les scores et métriques sont écrits dans la feuille Google Sheet `leads_audites`.
Les captures d'écran sont stockées dans `auditeur/screenshots/`.
