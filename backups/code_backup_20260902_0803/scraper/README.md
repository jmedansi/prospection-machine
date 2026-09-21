# Scraper Agent

Cet agent permet de rechercher des établissements locaux via **Google Places API**, d'extraire leurs informations détaillées, de chercher leurs emails via **Hunter.io**, de valider ces emails avec l'API gratuite **Mailcheck.ai**, puis d'enregistrer les leads validés dans un Google Sheets `leads_bruts`.

## Fonctionnalités

1.  **Recherche Google Places** : Cherche les établissements en fonction d'un métier (keyword) et d'une ville (city).
2.  **Détails Google Places** : Récupère les données complètes (nom, adresse, site web, téléphone, ID GMB, note, nombre d'avis, statut).
3.  **Recherche d'emails** : Utilise Hunter.io pour trouver un email associé au domaine du site web. Gère les limites d'utilisation via `config_manager`.
4.  **Validation d'emails** : Vérifie l'existence et la validité de l'email via mailcheck.ai.
5.  **Export vers Google Sheets** : Ajoute les leads valides dans la feuille `leads_bruts`.

## Installation

1. S'assurer que les dépendances sont installées : `pip install -r requirements.txt`
2. Configurer les clés API dans la feuille `config_comptes` gérée par `config_manager`.

## Utilisation

```bash
python main.py --keyword restaurant --city Cotonou
```

L'agent va afficher les 5 premiers résultats dans le terminal avant de commencer à les écrire dans Google Sheets.
