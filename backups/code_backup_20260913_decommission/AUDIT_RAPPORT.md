# Rapport de révision — 11 Mars 2026

## Corrections appliquées

- **Encodage UTF-8** : Ajout de `# -*- coding: utf-8 -*-` sur l'ensemble des scripts Python (`scraper/main.py`, `auditeur/main.py`, `config_manager.py`, `setup_sheets.py` et les 3 agents) pour prévenir les crashs liés aux accents (villes, noms d'entreprises).
- **Timeouts d'API (15s)** : Sécurisation de tous les appels externes `requests.get()` dans `scraper/main.py` (API Hunter, Mailcheck, requêtes web) pour éviter que la machine ne reste bloquée indéfiniment.
- **Validation d'URL robuste** : Modification stricte de la condition dans l'orchestrateur `auditeur/main.py` pour contourner le web_analyzer si le _site_web_ n'est pas une URL HTTP/HTTPS bien structurée.
- **Réparation Gspread 6.0** : 
  - Modification de l'appel de mise à jour des entêtes dans `setup_sheets.py` (`worksheet.update(values=..., range_name=...)`).
  - Ajout des `expected_headers` dans `get_all_records` (sur `setup_sheets.py` et `config_manager.py`) pour que gspread ne lève plus de crash si la feuille de config est momentanément vide ou asymétrique.
- **Requirements.txt** : Ajout de toutes les dépendances importées mais non listées (`requests>=2.31.0`, `beautifulsoup4>=4.12.0`, `openai>=1.0.0`, `google-genai>=0.1.0`).
- **Mode CLI pour l'auditeur** : Ajout du script argument parser (`argparse`) directement au sein d'`auditeur/main.py` pour autoriser le `--dry-run` et la commande `--limit`.
- **Test standalone config_manager** : Ajout d'un bloc `if __name__ == '__main__':` pour vérifier de façon autonome l'état de la connexion gspread.

## Tests effectés sur l'infrastructure

- ✅ **TEST 1 — Config** : `python config_manager.py` réussi (Compte détecté correctement).
- ✅ **TEST 2 — Sheets** : `python setup_sheets.py` réussi, création évitée s'ils existent et réparation de l'exception Gspread sur le mapping des entêtes.
- ✅ **TEST 3 — Auditeur sur URLs connues** : `python auditeur/test_auditeur.py` réussi sur 3 établissements. Notation et priorisation calculée correctement, fallback fonctionnel sur Google Maps.
- ✅ **TEST 4 — Dry run complet** : `python auditeur/main.py --dry-run --limit 2` réussi sans erreur, le print console des arguments et emails de Jean-Marc s'effectue bien sans polluer `leads_audites`.

## Points d'attention
- **Temps de parsing Groq Final** : Un email complexe peu visuel s'écrit rapidement sur LLaMA-3 Groq (le modèle Grok de xAI est également supporté en fallback si la clé `xai-` est détectée). Il faut s'assurer d'avoir un compte Groq actif de préférence.
- **Quotas PageSpeed Insights** : Une IP exécutant des centaines de passages sans clé API sur PageSpeed risque temporairement le Rate-Limit. Une pause de 3 secondes actuelle est minimale mais optimale à surveiller.

## Prochaines étapes recommandées
1. **Lancement Pilote** : Faire tourner le Scraper sur ~30 résultats réels, puis brancher l'Auditeur en production.
2. **Synchronisation d'Envoi (Brevo / Outil Cold Email)** : Utiliser le SDK de l'outils email pour déclencher les séquences avec l'identifiant "Thomas".
3. **Mise en Tâche Automatisée (Cron)** : Envisager d'héberger le pipeline sur un VPS (ou GitHub Actions) avec un interval programmé pour une prospection passive 100% autonome.
