---
name: debug-agent
description: Activated when the user mentions a bug, error, or asks to fix something. Provides a systematic debugging protocol.
---

# Protocole de débogage

## Étapes dans l'ordre
1. Lire errors.log → identifier la dernière erreur
2. Identifier le fichier et la ligne concernés
3. Reproduire l'erreur avec le cas minimal possible
4. Proposer la correction AVANT de l'appliquer
5. Appliquer seulement après confirmation
6. Relancer le test pour valider

## Vérifications systématiques
- Vérifier que le .env contient toutes les variables nécessaires
- Vérifier que la feuille Sheets ciblée existe et a les bons headers
- Vérifier que les dépendances sont installées (pip list)
- Vérifier que config_manager.get_config() retourne un dict non vide

## Jamais faire
- Ne jamais modifier requirements.txt sans proposer d'abord
- Ne jamais supprimer du code fonctionnel pour corriger un bug
- Ne jamais ignorer un warning Python
