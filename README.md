# Prospection Machine AI 🚀

Système automatisé de scraping Google Maps et d'audit technique pour la génération de prospects ultra-qualifiés.

## Installation rapide

```powershell
pip install -r requirements.txt
playwright install chromium
```

## Utilisation Autonome

Pour lancer une session de prospection complète (Scraping + Audit) sans aide extérieure :

```powershell
# Commande magique
python run_machine.py --keyword "VOTRE_METIER" --city "VOTRE_VILLE" --limit 10
```

### Paramètres disponibles :
- `--keyword`: Le métier recherché (ex: "restaurant").
- `--city`: La ville cible (ex: "Cotonou").
- `--limit`: Nombre maximum de leads à collecter (défaut: 10).
- `--dry-run`: Pour tester sans écrire dans Google Sheets.

## Architecture

1. **Scrapper** (`scraper/main.py`) : Utilise Playwright pour trouver les entreprises et extraire emails/téléphones. Stocke un "JSON Complet" pour plus de fiabilité.
2. **Auditeur** (`auditeur/main.py`) : Analyse la vitesse (PageSpeed), le SEO et la fiche Google Business.
3. **Copywriter (Jean-Marc)** : Rédige un e-mail personnalisé basé sur UN SEUL problème prioritaire.

## Résultats
- `leads_bruts` : Liste brute extraite avec le JSON complet.
- `leads_audites` : Audit technique détaillé et brouillon d'e-mail.

---
*Machine de prospection développée avec Antigravity.*
