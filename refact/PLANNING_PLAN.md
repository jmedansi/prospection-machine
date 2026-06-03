# PLANNING DU PLAN (META-PLAN)

Ce document définit les étapes rigoureuses pour aboutir au **Plan de Structure Réel** et au **Manifeste Technique** du projet Prospection Machine.

## OBJET
Éviter l'improvisation lors de la refonte modulaire. Avant de toucher au code, nous devons avoir une cartographie parfaite et un lexique unifié.

---

## ÉTAPE 1 : AUDIT & MAPPING (L'État des lieux)
*Objectif : Tout lister pour ne rien oublier.*

- **Audit Database :** Mapper chaque table et colonne SQLite. Identifier les doublons et les incohérences de langue (ex: `ville` vs `city`).
- **Audit API :** Répertorier toutes les routes, leurs paramètres (Fr/En) et leurs formats de retour.
- **Audit Frontend :** Analyser le fichier `dashboard-v4.html` (~4600 lignes) pour isoler les blocs logiques (Sidebar, Tabs, Formulaires, Logique JS).

## ÉTAPE 2 : HARMONISATION CONCEPTUELLE (Le Manifeste)
*Objectif : Définir la Loi.*

- **Lexique Unifié :** Décider des noms officiels (ex: `Lead`, `Campaign`, `Audit`).
- **Arbitrage Linguistique :** Fixer les règles (ex: Code/API en Anglais, Interface en Français).
- **Contrats de Données :** Définir la structure standard d'un objet "Lead" entre le Repo, l'API et le Frontend.

## ÉTAPE 3 : CONCEPTION CIBLE (Le Blueprint)
*Objectif : Dessiner la nouvelle structure.*

- **Arborescence de Fichiers :** Définir l'emplacement des futurs composants (`/dashboard/components/`, `/core/services/`, etc.).
- **Schéma de Communication :** Définir comment la donnée circulera entre les nouvelles couches.

## ÉTAPE 4 : STRATÉGIE DE MIGRATION (Le Plan de Travail)
*Objectif : Préparer l'exécution.*

- **Découpage par Modules :** Établir l'ordre de priorité (ex: 1. Sidebar, 2. API Leads, 3. Dashboard Central).
- **Gestion du Legacy :** Assurer la cohabitation entre le vieux monolithe et les nouveaux modules pendant la transition.

---

> [!IMPORTANT]
> Ce document est une **feuille de route de conception**. Une fois ces 4 étapes réalisées, nous produirons le **Plan de Structure Réel** qui sera le seul guide pour l'exécution technique.
