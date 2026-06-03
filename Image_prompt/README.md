# 🎨 Module Image_prompt

## Rôle
Ce module est responsable de la génération de prompts visuels haute fidélité pour enrichir les audits de prospection. Il permet de créer des images "maquettes" ou des illustrations de problèmes techniques (vitesse, SEO, design) via des IA génératrices d'images.

## Structure
- `prompt_generator.py` : Logique de construction des prompts (via templates Jinja2 ou f-strings).
- `image_service.py` : Client pour les APIs de génération (OpenAI, Midjourney API, etc.).
- `templates/` : Stockage des modèles de prompts par industrie et par type de problème.

## Flux de données
1. **Input** : `lead_data` (nom, secteur, score audit, problème principal).
2. **Process** : Sélection du template → Injection des variables → Raffinement du prompt.
3. **Output** : Un string (prompt) ou une URL d'image générée.

## Règles
- Ne jamais générer d'images offensantes ou trompeuses.
- Prioriser le style "Premium SaaS / Modern Web Design".
- Toutes les images générées doivent être stockées de manière persistante avant d'être envoyées.
