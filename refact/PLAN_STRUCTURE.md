# PLAN DE STRUCTURE (EN COURS)

Ce document est le "Plan de Structure Réel", construit étape par étape selon la méthodologie définie dans [PLANNING_PLAN.md](PLANNING_PLAN.md).

---

## ÉTAPE 1 : AUDIT & MAPPING (L'État des lieux — VERSION ULTRA-COMPLÈTE)

### 1.1. Cartographie Exhaustive des Données & Conflits

#### 1.1.1 Colonnes par Table (Inventaire Complet)

| Table | Colonnes | Total |
| :--- | :--- | :--- |
| **leads_bruts** | `id`, `nom`, `adresse`, `site_web`, `telephone`, `email`, `email_valide`, `rating`, `nb_avis`, `category`, `mot_cle`, `ville`, `lien_maps`, `date_scraping`, `statut`, `sheets_synced`, `campaign_id`, `nom_gerant`, `prenom_gerant`, `linkedin_url`, `source`, `tag_urgence`, `niveau_urgence`, `donnees_audit` | 24 |
| **leads_audites** | `id`, `lead_id`, `mobile_score`, `desktop_score`, `tablet_score`, `lcp_ms`, `fcp_ms`, `cls`, `render_blocking_scripts`, `uses_cache`, `page_size_kb`, `has_https`, `has_meta_description`, `title_length`, `h1_count`, `has_schema`, `has_contact_button`, `tel_link`, `images_without_alt`, `has_analytics`, `has_robots`, `has_sitemap`, `has_responsive_meta`, `cms_detected`, `visible_text_words`, `score_performance`, `score_seo`, `score_gmb`, `score_urgence`, `top3_problems`, `service_suggere`, `probleme_principal`, `arguments`, `rapport_resume`, `email_objet`, `email_corps`, `approuve`, `lien_rapport`, `lien_pdf`, `date_audit`, `statut`, `sheets_synced`, `template_used`, `rapport_html`, `screenshot_desktop`, `screenshot_mobile`, `profile`, `nb_avis`, `notified_at`, `template_variant`, `statut_prospection`, `email_valide`, `email_source`, `copywriting_mode`, `ceo_prenom`, `ceo_nom`, `ceo_source`, `telephone_sniper`, `mx_host`, `is_catch_all`, `linkedin_url` | 61 |
| **emails_envoyes** | `id`, `lead_id`, `message_id_brevo`, `date_envoi`, `email_objet`, `email_corps`, `lien_rapport`, `statut_envoi`, `ouvert`, `date_ouverture`, `nb_ouvertures`, `repondu`, `date_reponse`, `type_reponse`, `rdv_confirme`, `date_rdv`, `notes`, `sheets_synced`, `clique`, `date_clic`, `bounce`, `spam`, `message_id_resend`, `email_destinataire`, `tracking_token`, `relance_count`, `template_variant`, `message_erreur`, `nb_tentatives_envoi`, `date_dernier_essai`, `derniere_interaction`, `date_dernier_clic`, `date_premiere_ouverture`, `lead_temperature`, `date_derniere_ouverture`, `nb_clics`, `score_lead`, `ip_ouverture`, `date_relance_prevue`, `relance_type`, `user_agent_ouverture` | 41 |
| **campagnes** | `id`, `nom`, `secteur`, `ville`, `date_creation`, `total_leads`, `statut`, `nb_demande` | 8 |
| **planned_campaigns** | `id`, `secteur`, `keyword`, `city`, `limit_leads`, `date_planifiee`, `heure`, `statut`, `campaign_id`, `created_at`, `min_emails` | 11 |
| **planning_settings** | `key`, `value` | 2 |
| **scraping_priorities** | `id`, `secteur`, `keyword`, `ville`, `limit_leads`, `priorite`, `actif`, `frequence_jours`, `derniere_execution`, `created_at`, `min_emails` | 11 |
| **email_events** | `id`, `email_record_id`, `lead_id`, `event_type`, `event_data`, `timestamp` | 6 |
| **email_sequences** | `id`, `lead_id`, `email_record_id`, `email_type`, `statut`, `date_planifiee`, `date_envoi`, `condition_envoi`, `created_at` | 9 |
| **resend_accounts** | `id`, `api_key`, `sender_email`, `sender_name`, `daily_usage`, `last_reset`, `actif` | 7 |
| **scheduled_batches** | `id`, `batch_key`, `scheduled_at`, `status`, `nb_emails`, `lead_ids`, `message_ids`, `created_at` | 8 |
| **sync_log** | — | — |
| **scheduler_log** | — | — |
| **review_machine_runs** | — | — |

#### 1.1.2 Conflits de Nomenclature Identifiés

| Concept | Champ DB principal | Doublons / Variantes identifiées | État de Normalisation |
| :--- | :--- | :--- | :--- |
| **Identité Lead** | `nom` (`leads_bruts`) | `prospect_nom`, `lead_name` | **Conflit critique Fr/En** |
| **Secteur / Niche** | `category` (`leads_bruts`) | `secteur`, `sector`, `niche` | **Dispersion maximale** (4 termes) |
| **Localisation** | `ville` (`leads_bruts`) | `city` (`planned_campaigns`) | Mixte Fr/En |
| **Contact Email** | `email` | `email_valide`, `email_source` | Fragmenté |
| **Performance Web** | `lcp_ms` | `fcp_ms`, `cls`, `score_performance` | Harmonisation de l'unité requise |
| **Tracking Email** | `ouvert`, `clique`, `repondu` | `nb_ouvertures`, `date_clic`, `type_reponse`| Structure OK mais nomenclatures variables |
| **Configuration** | `config_comptes` (Sheets) | `.env`, `planning_settings` (SQLite) | Dualité entre Cloud (Sheets) et Local |

### 1.2. AUDIT EXHAUSTIF DES ROUTES API (L'état actuel du désordre)

| Catégorie | Route | Méthode | Paramètres | Observations / Conflits |
| :--- | :--- | :--- | :--- | :--- |
| **Leads** | `/api/leads` | GET | `statut`, `email`, `sector` | Standard. Utilise `sector` (En). |
| | `/api/leads/<id>` | GET | — | Standard. |
| | `/api/lead/update` | PUT | `id` (body) | **Incohérence** : singulier (`lead`) vs pluriel ailleurs. |
| | `/api/lead/delete` | DELETE | `id` (query) | **Incohérence** : singulier. |
| | `/api/leads/batch-delete`| POST | `ids`, `noms` | Devrait être DELETE. Doublon avec `delete_batch`. |
| | `/api/sectors` | GET | — | Doublon avec `/api/leads/sectors`. |
| **Audits** | `/api/audit/launch` | POST | `lead_ids`, `limit` | — |
| | `/api/audit/cleanup` | POST | `lead_id` | Utilise `lead_id` (vs `id` ailleurs). |
| **Campagnes**| `/api/scraper/launch` | POST | `keyword`, `city` | — |
| | `/api/campaigns` | GET | `date_start`, `date_end`| — |
| | `/api/planning` | GET/POST| `limit_leads` | Utilise `limit_leads` (vs `nb_demande` en DB). |
| **Emails** | `/api/email/generate` | POST | `lead_ids` | — |
| | `/api/email/send` | POST | `lead_ids` | Doublon avec `/api/email/send-approved`. |
| | `/api/crm` | GET | `filter`, `limit` | Supporte alias `emails` pour le retour. |
| **Stats** | `/api/stats` | GET | `campaign_id` | — |
| | `/api/stats/niche` | GET | — | Doublon avec `/api/stats/niches`. |
| **Rapports** | `/api/previews` | GET | — | Doublon avec `/api/rapports`. |
| | `/api/previews/push` | POST | `slugs` | — |
| **Santé** | `/api/health` | GET | — | Structure de retour unique. |

### 1.3. Inventaire des "Moteurs" (Logique Métier)

| Module | Rôle | Dépendances critiques |
| :--- | :--- | :--- |
| **Pipeline Auto** | `dashboard/pipeline/` | Orchestration `batch_management`, `notifications`, `scraper_loop`. |
| **Rotation LLM** | `config_manager.py` | Quotas temps réel sur Google Sheets (`config_comptes`). |
| **Scheduler** | `dashboard/scheduler.py` | APScheduler + Polling `pending.db` (Telegram Hub). |
| **Registry** | `core/pipeline_registry.py` | Découverte modulaire des tâches planifiées. |

### 1.4. Audit du Dashboard Monolithique (`dashboard-v4.html`)

- **Frontend** : 4600 lignes.
- **State JS** : ~50 variables `_active...` (global scope).
- **Logique Redondante** : `synthProbleme` (JS) vs `analysis` (Python).

### 1.5. Audit des Templates

- **Emails de Prospection** : 4 variants (`template_profil_a` à `d`) dans `templates/emails/`.
- **Rapports Publics** : 4 templates correspondants dans `templates/rapports/` (HTML + Maquettes).

---

## ÉTAPE 2 : HARMONISATION CONCEPTUELLE (Le Manifeste)

Ce manifeste définit les règles immuables pour la suite de la refonte. Tout nouveau code doit s'y conformer.

### 2.1. Le Lexique Officiel (Data & API)

Désormais, nous utilisons exclusivement ces noms dans la couche de données (Repo, API, JSON) :

| Concept | **Nom Standard (Code)** | Exemples de suppression |
| :--- | :--- | :--- |
| **Entreprise** | **`name`** | `nom`, `prospect_nom` |
| **Secteur** | **`sector`** | `category`, `secteur`, `niche` |
| **Localisation** | **`city`** | `ville` |
| **Site Web** | **`website`** | `site_web` |
| **Note Google** | **`rating`** | `note` |
| **Nb d'avis** | **`review_count`** | `nb_avis`, `avis` |
| **Statut** | **`status`** | `statut`, `statut_prospection` |
| **Date Création** | **`created_at`** | `date_scraping`, `date_audit` |

---

#### 2.1.1 Contrat de Données — Étape SCRAPER (→ leads_bruts)

```json
{
  "nom": "string",
  "adresse": "string",
  "site_web": "string",
  "telephone": "string",
  "rating": "float",
  "nb_avis": "integer",
  "email": "string",
  "email_valide": "string (valid|invalid|unknown)",
  "email_source": "string",
  "date_scraping": "ISO8601",
  "mot_cle": "string",
  "ville": "string",
  "category": "string",
  "lien_maps": "string",
  "campaign_id": "integer",
  "statut": "string (en_attente|scraped|audite|a_contacter|envoye)",
  "nom_gerant": "string",
  "prenom_gerant": "string",
  "linkedin_url": "string",
  "source": "string (maps|manual|sniper)"
}
```

#### 2.1.2 Contrat de Données — Étape AUDITEUR (→ leads_audites)

61 CHAMPS — Métriques Web + Technique + Scores + Problemátiques

```json
{
  // === Index Lead ===
  "lead_id": "integer",
  
  // === Métriques Web (PageSpeed) ===
  "mobile_score": "integer (0-100)",
  "desktop_score": "integer (0-100)",
  "tablet_score": "integer (0-100)",
  "lcp_ms": "float",
  "fcp_ms": "float",
  "cls": "float",
  "render_blocking_scripts": "integer",
  "uses_cache": "integer",
  "page_size_kb": "float",
  
  // === Technique HTML ===
  "has_https": "integer (0/1)",
  "has_meta_description": "integer (0/1)",
  "title_length": "integer",
  "h1_count": "integer",
  "has_schema": "integer (0/1)",
  "has_contact_button": "integer (0/1)",
  "tel_link": "integer (0/1)",
  "images_without_alt": "integer",
  "has_analytics": "integer (0/1)",
  "has_robots": "integer (0/1)",
  "has_sitemap": "integer (0/1)",
  "has_responsive_meta": "integer (0/1)",
  "cms_detected": "string",
  "visible_text_words": "integer",
  
  // === Scores (Calculés) ===
  "score_performance": "integer (0-100)",
  "score_seo": "integer (0-100)",
  "score_gmb": "integer (0-100)",
  "score_urgence": "float (0-10)",
  
  // === Problematiques (Detectées) ===
  "top3_problems": "JSON array",
  "probleme_principal": "string",
  "service_suggere": "string",
  "arguments": "JSON array",
  
  // === Copiendwriter (généré après) ===
  "rapport_resume": "string",
  
  // === Email (généré par email_builder) ===
  "email_objet": "string",
  "email_corps": "string",
  "approuve": "integer (0/1)",
  
  // === Rapports ===
  "lien_rapport": "string",
  "lien_pdf": "string",
  "rapport_html": "string",
  "screenshot_desktop": "string",
  "screenshot_mobile": "string",
  
  // === Métadonnées ===
  "profile": "string (A|B|C|D)",
  "template_used": "string",
  "template_variant": "string",
  "statut": "string",
  "date_audit": "ISO8601",
  "email_valide": "string",
  "email_source": "string",
  "copywriting_mode": "string",
  "ceo_prenom": "string",
  "ceo_nom": "string",
  "ceo_source": "string",
  "telephone_sniper": "string",
  "mx_host": "string",
  "is_catch_all": "integer (0/1)",
  "linkedin_url": "string"
}
```

#### 2.1.3 Contrat de Données — Étape COPYWRITER (→ enrichissement leads_audites)

```json
{
  "phrase_synthese": "string (ex: 'Bon GMB, mauvais site')",
  "diagnostic": "string (argument commercial personnalisé)",
  "rapport_resume": "string",
  "service_propose": "string",
  "probleme_principal": "string",
  "arguments": "JSON array"
}
```

#### 2.1.4 Contrat de Données — Étape EMAIL BUILDER (→ EMAIL HTML)

```json
{
  "email_objet": "string (depuis <title> du template HTML)",
  "email_corps": "HTML string",
  "template_used": "string",
  "template_variant": "string"
}
```

#### 2.1.5 Contrat de Données — Étape ENVOI (→ emails_envoyes)

```json
{
  "lead_id": "integer",
  "message_id_resend": "string",
  "email_destinataire": "string",
  "email_objet": "string",
  "email_corps": "string",
  "lien_rapport": "string",
  "statut_envoi": "string (pending|sent|delivered|bounced)",
  "date_envoi": "ISO8601",
  "ouvert": "integer (0/1)",
  "date_ouverture": "ISO8601",
  "nb_ouvertures": "integer",
  "clique": "integer (0/1)",
  "date_clic": "ISO8601",
  "repondu": "integer (0/1)",
  "date_reponse": "ISO8601",
  "type_reponse": "string",
  "rdv_confirme": "integer (0/1)",
  "date_rdv": "ISO8601",
  "bounce": "integer (0/1)",
  "spam": "integer (0/1)",
  "relance_count": "integer",
  "relance_type": "string",
  "template_variant": "string"
}
```

#### 2.1.6 Conventions de Serialisation JSON

- **`null`** pour champs absents (jamais de clé manquante)
- **`ISO8601`** pour toutes les dates (`2024-01-15T10:30:00Z`)
- **`snake_case`** pour toutes les clés JSON
- **`boolean`** : `true`/`false` (jamais `1`/`0`)
- **`integer`** : pas de décimales (utiliser `0/1` pour champs SQL)
- **`float`** : séparateur point (`.`) jamais virgule

### 2.2. Conventions de Développement

- **Langues** : 
    - **Anglais** : Base de données, Endpoints API, Variables de code, Commentaires techniques.
    - **Français** : Textes de l'interface (UI), Messages d'erreur utilisateur, Logs de haut niveau.
- **Nomenclature** :
    - **Python** : `snake_case` pour tout.
    - **JavaScript** : `camelCase` pour le code, `snake_case` pour les clés des objets venant de l'API.
- **API (Standard V1)** :
    - Ressources au pluriel (`/api/leads`, `/api/campaigns`).
    - Utilisation des verbes HTTP réels : `GET` (lecture), `POST` (création/action), `PUT` (update complet), `PATCH` (update partiel), `DELETE` (suppression).
    - Format de retour uniforme : `{ "status": "success", "data": {...} }`.

---

## ÉTAPE 3 : ARCHITECTURE CIBLE (Le Blueprint)

Cette étape définit la nouvelle organisation physique du code pour isoler les responsabilités.

### 3.1. Arborescence de Dossiers Cible

```text
dashboard/
├── templates/
│   ├── base.html             # Squelette (HTML5, Meta, CSS globaux, Nav)
│   ├── components/           # Fragments Jinja2 (Réutilisables)
│   │   ├── layout/           # sidebar.html, header.html, footer.html
│   │   ├── widgets/          # stats_card.html, gauge_score.html
│   │   └── leads/            # lead_row.html, audit_panel.html
│   └── views/                # Pages complètes (Extends base.html)
│       ├── cockpit.html      # Vue Dashboard / Stats
│       ├── campaigns.html    # Vue Pipeline / Leads
│       └── settings.html     # Vue Config / LLM
├── static/
│   ├── css/
│   │   ├── core.css          # Reset, Variables (CSS Vars), Typography
│   │   └── components/       # Styles isolés par fragment
│   └── js/
│       ├── core/             # api.js (Comm standardisée), app_state.js
│       └── modules/          # Logique par page (leads.js, cockpit.js)
└── routes/                   # Blueprints Python (Inchangés mais nettoyés)
```

### 3.2. Stratégie de Découpage du Monolithe

Nous allons "déshabiller" `dashboard-v4.html` (4600 lignes) selon cet ordre :

1.  **Extraction du CSS** : Déplacer tous les styles vers `static/css/core.css` et utiliser des variables CSS pour le thème sombre/clair.
2.  **Création du Squelette (`base.html`)** : Extraire le `head`, la navigation `mobile-app` et la `sidebar`.
3.  **Migration des "Vues"** : Isoler chaque onglet (Cockpit, Campagne, Sniper) dans son propre fichier dans `views/`.
4.  **Modularisation JS** : Isoler les fonctions de `ui.js` et les scripts inline dans `static/js/modules/`.

### 3.3. Isolation de la Logique Métier

- Les calculs de score (`synthProbleme`) seront déplacés dans un service Python dédié (`services/logic/scoring.py`) pour garantir qu'un seul code fait le calcul, évitant les écarts entre l'API et l'Interface.

### 3.4. Schéma de Communication (Intégré)

#### 3.4.1 Flux de Données (Pipeline Complet)

| Étape | Entrée | Sortie | Table DB | Agent Python |
|:--- |:--- |:--- |:--- |:--- |
| **Scraping** | `keyword`, `city` | `leads_bruts` | `leads_bruts` | `scraper/main.py` |
| **Email Finding** | `website` | `email` | `leads_bruts.email` | `scraper/email_finder.py` |
| **Audit Tech** | `lead_id`, `site_web` | `leads_audites` | `leads_audites` | `auditeur/main.py` |
| **GMB Extract** | `nom`, `ville` | `rating`, `nb_avis` | `leads_audites` | `auditeur/agents/gmb_extractor.py` |
| **Copywriting** | `audit_dict` | `phrase_synthese` | `leads_audites` | `copywriter/main.py` |
| **Email Gen** | `phrase_synthese` | `email HTML` | `emails_envoyes` | `envoi/email_builder.py` |
| **Envoi** | `lead_id` | `emails_envoyes` | `emails_envoyes` | `envoi/resend_sender.py` |
| **Tracking** | `webhook` | `email_events` | `email_events` | `workers/resend_polling_service.py` |

#### 3.4.2 Architecture des Appels

```
[Frontend JS] → [Dashboard Routes] → [Services] → [Repos] → [SQLite]
[Workers]   → [Services]       → [Repos] → [SQLite]
```

#### 3.4.3 Format Standard des Réponses API

```json
// Succès (GET)
{
  "status": "success",
  "data": { "leads": [...] },
  "meta": { "page": 1, "total": 100 }
}

// Succès (POST/PUT)
{
  "status": "success", 
  "data": { "id": 123 },
  "message": "Action effectuee"
}

// Erreur
{
  "status": "error",
  "error": "CODE_ERROR",
  "message": "Description erreur"
}
```

#### 3.4.4 Workers & Scheduler

| Worker | Frequence | Action |
|:--- |:--- |:--- |
| **scraping_loop** | Toutes les heures | `scraper_runner.run_batch()` |
| **audit_loop** | Quotidien | `audit_runner.run_pending()` |
| **email_sender** | 14h00 | `resend_sender.send_approved()` |
| **resend_polling** | 15min | `polling_service.check_events()` |
| **sequence_relance** | J+2, J+5 | `sequence_service.send_relance()` |

#### 3.4.5 Points d'Entree

| Composant | Type | Endpoint |
|:--- |:--- |:--- |
| **Frontend** | HTTP | `/`, `/dashboard-v4.html` |
| **API Routes** | HTTP | `/api/leads`, `/api/campaigns`, `/api/emails` |
| **Scheduler** | Cron | `workers/scheduler.py` |
| **Webhook** | HTTP | `/api/webhooks/resend` |
| **CLI** | Shell | `python run_machine.py` |

---

## ÉTAPE 4 : STRATÉGIE DE MIGRATION (L'Action)

Pour garantir une stabilité totale, nous utiliserons une approche par **"Shadowing"** (en parallèle) et non par remplacement brutal.

### 4.1. Phase de Coexistence (Shadowing)
1.  **Création du squelette** : Le fichier `base.html` sera créé.
2.  **Route de Test** : Une nouvelle route `/dashboard-v5` sera créée pour pointer vers la nouvelle structure.
3.  **Résultat** : L'ancien dashboard reste accessible sur `/` (ou l'URL habituelle), nous permettant de comparer les deux versions en temps réel.

### 4.2. Migration Progressive par Composant
1.  **Migration du Sourcing (Radar)** : Extraire la logique de Sourcing, la modulariser, et l'afficher dans `/dashboard-v5`.
2.  **Migration de la Prospection (Studio)** : Même processus.
3.  **Validation** : Chaque onglet migré doit être testé sur mobile et desktop pour vérifier qu'aucune fonctionnalité n'a été perdue.

### 4.3. Bascule Finale (The Switch)
1.  Une fois tous les composants validés sur la nouvelle architecture, la route principale `/` sera redirigée vers la nouvelle vue.
2.  Le fichier `dashboard-v4.html` sera archivé (déplacé dans un dossier `legacy/`) mais conservé par sécurité pendant une semaine.

### 4.4. Gestion de la Donnée

- **Alias Logic** : Dans un premier temps, nous ne modifions pas les noms des colonnes SQLite (trop risqué pour les agents en cours d'exécution).
- **Mapping Repo** : Les Repositories serviront de couche de traduction. Ils liront `nom` en DB mais retourneront `name` à l'API.

### 4.5. Ordre de Priorité (Découpage Détaillé)

| Priorité | Module | Estimation | Dépendances |
|:--- |:--- |:--- |:--- |
| **1** | Extraction CSS/Themes | 2h | Aucune |
| **2** | Base.html (Skeleton) | 1h | CSS |
| **3** | Sidebar + Header | 2h | Base.html |
| **4** | Cockpit View | 4h | Sidebar |
| **5** | Leads View | 4h | API Routes |
| **6** | Campaigns View | 4h | API Routes |
| **7** | Settings View | 2h | Config |
| **8** | API Routes normalisées | 4h | Repos |
| **9** | Switch final | 1h | Toutes |

**Total estimé : 24h** (3 jours ouvrés)

### 4.6. Critères de Validation (Definition of Done)

Pour qu'un module soit considéré comme **validé**, les conditions suivantes doivent être remplies :

- [ ] **Tests unitaires** : Toutes les fonctions du module passent
- [ ] **Tests E2E** : Le parcours utilisateur complet fonctionne
- [ ] **Responsive** : Affichage correct sur mobile (320px) + desktop (1920px)
- [ ] **Performance** : Temps de chargement < 2s
- [ ] **Logs** : Pas d'erreurs dans la console navigateur
- [ ] **Retrocompatibilité** : L'ancien dashboard reste fonctionnel

### 4.7. Plan de Rollback

Si une migration échoue (plus de 5% d'erreurs ou fonctionnalité cassée) :

| Phase | Action Rollback |
|:--- |:--- |
| **Pendant migration** | Revenir à l'URL précédente (`/dashboard-v4.html`) |
| **Après switch** | Redéployer l'ancienne version depuis `git` |
| **DB** | Les Repos font abstraction — pas de rollback DB nécessaire |

### 4.8. Timeline Détaillée

```
Semaine 1 : Extraction CSS + Skeleton + Layout
    - Lun: Extraction CSS (2h)
    - Mar: Base.html (1h)
    - Mer: Sidebar + Header (2h)
    - Jeu: Tests layout (2h)

Semaine 2 : Vues principales
    - Lun: Cockpit View (4h)
    - Mar: Leads View (4h)
    - Mer: Campaigns View (4h)
    - Jeu: Settings View (2h)

Semaine 3 : API + Integration
    - Lun: API Routes normalisées (4h)
    - Mar: Intégration Frontend (4h)
    - Mer: Tests E2E (4h)
    - Jeu: Fix bugs (4h)

Semaine 4 : Switch + Validation
    - Lun:Shadowing /dashboard-v5 (2h)
    - Mar: Comparaison visuelle (2h)
    - Mer: Switch final (1h)
    - Jeu-Ven: Monitoring + cleanup
```

---

**LE PLAN DE STRUCTURE EST DÉSORMAIS COMPLET À 100%.**
