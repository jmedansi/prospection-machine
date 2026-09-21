# Prospection Machine - Documentation Technique

**Version:** 2.0 (Architecture modulaire)  
**Date:** 2026-04-04  
**Statut:** Production

---

## Vue d'ensemble

Prospection Machine est un systeme automatise de prospection B2B qui scrape, audite, redige et envoie des emails personnalises a des entreprises locales.

**Pipeline:**
```
Google Maps Scraping -> Audit Technique -> Copywriting IA -> Validation Telegram -> Envoi Resend -> Tracking
```

**Demarrage:**
```bash
python dashboard/app.py        # Dashboard + Scheduler sur http://localhost:5001
python -m workers.scheduler    # (Optionnel) Polling Resend fallback
```

---

## Architecture

```
prospection-machine/
|
|-- core/                          # Fondations partagees
|   |-- config.py                  # Chargement .env centralise (ensure_env)
|   |-- telegram_adapter.py        # Adaptateur unique vers D:/hub_telegram
|   |-- pipeline_registry.py       # Registre central des pipelines (PipelineRegistry)
|
|-- database/                      # Acces SQLite, decoupe par domaine
|   |-- connection.py              # get_conn(), DB_PATH, WAL mode
|   |-- schema.py                  # init_db(), migrations, register_schema()
|   |-- leads.py                   # CRUD leads_bruts + transitions statut
|   |-- audits.py                  # CRUD leads_audites
|   |-- emails.py                  # CRUD emails_envoyes + email_events
|   |-- campaigns.py               # CRUD campagnes
|   |-- stats.py                   # Requetes d'agregation dashboard
|   |-- crm.py                     # Suivi reponses et RDV
|   |-- sync.py                    # Log de synchronisation
|   |-- db_manager.py              # Shim retrocompat (re-exporte tout)
|
|-- dashboard/                     # Serveur Flask
|   |-- app.py                     # App factory (create_app) ~80 lignes
|   |-- scheduler.py               # APScheduler (jobs planifies)
|   |-- auto_planner.py            # Planification auto des campagnes
|   |-- sequencer.py               # Sequences de relance
|   |-- routes/                    # Flask Blueprints
|   |   |-- leads.py               # /api/leads, /api/lead/*
|   |   |-- audits.py              # /api/audit/*
|   |   |-- emails.py              # /api/email/*
|   |   |-- campaigns.py           # /api/campaigns, /api/planning/*
|   |   |-- stats.py               # /api/stats/*
|   |   |-- scraping.py            # /api/scraping-priorities/*
|   |   |-- review.py              # /review
|   |   |-- pages.py               # / (sert le dashboard HTML)
|   |   |-- webhooks.py            # /api/webhooks/resend
|   |-- pipeline/                  # Pipeline de prospection (decoupe)
|       |-- lead_selection.py      # Selection des leads pour batch
|       |-- email_generation.py    # Generation email (copywriter + builder)
|       |-- report_publishing.py   # Publication rapports sur GitHub Pages
|       |-- batch_management.py    # Orchestrateur principal (maintain_batch_slots)
|       |-- approval.py            # Validation Telegram + auto-approbation
|       |-- notifications.py       # Notifications Telegram des batches
|       |-- scraper_loop.py        # Boucle scraping en arriere-plan
|
|-- scraper/                       # Scraping Google Maps
|   |-- main.py                    # Point d'entree (--keyword, --city, --limit)
|   |-- email_finder.py            # Extraction emails depuis sites web
|   |-- zone_agent.py              # Decouverte de zones geographiques
|
|-- auditeur/                      # Audit technique des sites
|   |-- main.py                    # Point d'entree (--ids)
|   |-- agents/
|       |-- web_analyzer.py        # PageSpeed, SEO, detection CMS
|       |-- gmb_extractor.py       # Donnees Google Business Profile
|       |-- business_copywriter.py # Analyse business
|
|-- copywriter/                    # Generation de contenu email
|   |-- main.py                    # Situations S1-S8, persona Jean-Marc
|
|-- envoi/                         # Envoi et tracking email
|   |-- email_builder.py           # Construction HTML depuis templates A/B/C/D
|   |-- resend_sender.py           # Envoi via Resend API
|   |-- brevo_sender.py            # Envoi via Brevo (fallback)
|   |-- email_tracking_service.py  # Enregistrement evenements webhook
|
|-- reporter/                      # Generation de rapports HTML
|   |-- main.py                    # Rapport audit interactif (publie sur GitHub Pages)
|
|-- synthetiseur/                  # Publication et assets
|   |-- github_publisher.py        # Push rapports vers GitHub Pages
|   |-- mockup_generator.py        # Maquettes pour profil A (sans site)
|   |-- image_storage.py           # Stockage screenshots
|
|-- enrichisseur/                  # Enrichissement leads
|   |-- ceo_finder.py              # Recherche prenom/nom du gerant
|
|-- services/                      # Services metier extraits
|   |-- email_sequence_service.py  # Gestion sequences de relance
|   |-- lead_scoring_service.py    # Scoring des leads
|
|-- workers/                       # Processus en arriere-plan
|   |-- resend_polling_service.py  # Polling API Resend (fallback webhook)
|   |-- scheduler.py               # Scheduler pour polling
|   |-- sequence_worker.py         # Worker relances
|
|-- modules/                       # Modules extensibles (plugins)
|   |-- review_machine/            # (Futur) Machine a avis Google
|
|-- templates/emails/              # Templates HTML email
|   |-- template_profil_a.html     # Pas de site web
|   |-- template_profil_b.html     # Site lent / mal optimise
|   |-- template_profil_c.html     # Mauvaise fiche GMB (note/avis)
|   |-- template_profil_d.html     # SEO incomplet
|
|-- config_manager.py              # Config Google Sheets + cache (legacy)
|-- data/prospection.db            # Base SQLite
```

---

## Core : Fondations partagees

### `core/config.py` - Configuration centralisee

Charge le `.env` une seule fois. Tous les modules appellent `ensure_env()` au lieu de `load_dotenv()`.

```python
from core.config import ensure_env, ROOT
ensure_env()
```

Variables exposees : `ROOT` (racine projet), `HUB_TELEGRAM` (chemin Telegram bot).

### `core/telegram_adapter.py` - Adaptateur Telegram

Seul fichier qui fait `sys.path.insert` vers `D:/hub_telegram`. Re-exporte :
- `send_validation_request()` - Envoie une demande de validation
- `check_pending_db()` - Verifie la reponse du bot
- `notify()` - Envoie une notification simple

### `core/pipeline_registry.py` - Registre de pipelines

Permet aux modules d'enregistrer leurs pipelines pour execution par le scheduler.

```python
from core.pipeline_registry import PipelineRegistry

PipelineRegistry.register("mon_pipeline", ma_fonction, interval_hours=2, description="...")
PipelineRegistry.get_all()  # -> dict de tous les pipelines enregistres
```

---

## Database : Acces par domaine

La base SQLite (`data/prospection.db`) est decoupee en modules par domaine. Chaque module importe `get_conn()` depuis `database.connection`.

### Styles d'import (tous fonctionnent)

```python
# Nouveau style (recommande)
from database.leads import insert_lead
from database.connection import get_conn

# Import package
from database import get_conn, insert_lead

# Retrocompat (deprecated, fonctionne toujours)
from database.db_manager import get_conn, insert_lead
```

### `database/connection.py`

| Fonction | Role |
|----------|------|
| `get_conn()` | Connexion SQLite avec WAL + foreign keys + row_factory |
| `_serialize_json()` | Serialise list/dict en JSON string |
| `_deserialize_json()` | Deserialise JSON string en Python |

### `database/schema.py`

| Fonction | Role |
|----------|------|
| `init_db()` | Cree toutes les tables si absentes |
| `migrate_db()` | Ajoute les colonnes manquantes (ALTER TABLE) |
| `register_schema(name, sql)` | Permet aux modules plugins d'ajouter leurs propres tables |

### `database/leads.py`

| Fonction | Role |
|----------|------|
| `insert_lead()` | Insertion avec deduplication (nom+ville ou telephone) |
| `get_leads_pending()` | Leads en attente de traitement |
| `get_all_leads()` | Liste filtree avec JOIN audit |
| `update_lead_statut()` | Changement de statut |
| `get_lead_by_id()` / `get_lead_by_name()` | Lookup |
| `delete_lead()` / `update_lead()` | CRUD |
| `transition_statut()` | Machine a etats (scrape -> en_attente -> audite -> email_genere -> envoye -> ...) |

### `database/audits.py`

| Fonction | Role |
|----------|------|
| `insert_audit()` | INSERT OR REPLACE avec serialisation JSON |
| `get_audits_ready_for_email()` | Audits avec email_corps, prets a envoyer |
| `get_audits_with_reports()` | Audits ayant un rapport publie |
| `update_audit_email()` | Met a jour objet + corps email |
| `update_audit_approval()` | Approuve/rejette par nom de lead |
| `update_audit_pdf()` | Met a jour le lien PDF |

### `database/emails.py`

| Fonction | Role |
|----------|------|
| `insert_email_sent()` | Enregistre un envoi (message_id Resend/Brevo) |
| `update_email_tracking()` | Webhook : met a jour ouvert/clique/bounce |
| `insert_email_event()` | Log evenement dans email_events |

### `database/campaigns.py`

| Fonction | Role |
|----------|------|
| `insert_campaign()` | Cree une campagne |
| `get_all_campaigns()` | Liste avec stats agregees (leads, envois, ouvertures) |
| `get_campaign_by_id()` | Detail campagne |
| `delete_campaign()` | Suppression |

### `database/stats.py`

| Fonction | Role |
|----------|------|
| `get_dashboard_stats()` | Agregation complete (~200 lignes) : pipeline, taux, scores |
| `get_leads_for_dashboard()` | Liste enrichie pour l'UI |
| `get_niche_performance()` | Performance par secteur+ville |
| `get_ab_test_performance()` | Resultats A/B test (v1 vs v2) |

### `database/crm.py`

| Fonction | Role |
|----------|------|
| `update_crm_manual()` | Notes manuelles, RDV, type reponse |
| `get_crm_counts()` | Compteurs : ouverts, cliques, repondus, positifs |
| `get_crm_data()` | Vue CRM filtree |

---

## Tables SQLite principales

| Table | Role | Colonnes cles |
|-------|------|---------------|
| `leads_bruts` | Prospects scrapes | id, nom, email, ville, category, site_web, telephone, rating, nb_avis, statut, campaign_id |
| `leads_audites` | Resultats d'audit | lead_id, mobile_score, lcp_ms, score_urgence, email_objet, email_corps, approuve, lien_rapport, template_variant |
| `emails_envoyes` | Emails envoyes | lead_id, message_id_resend, email_objet, email_corps, statut_envoi, ouvert, clique, bounce |
| `email_events` | Evenements webhook | email_record_id, lead_id, event_type (sent/opened/clicked/bounced), event_data, timestamp |
| `campagnes` | Groupes d'envoi | keyword, city, secteur, date_creation, nb_leads |
| `scheduled_batches` | Batches planifies Resend | batch_key, scheduled_at, status (pending/queued/sent), nb_emails, lead_ids, message_ids |
| `planning_settings` | Parametres systeme | key, value (daily_quota, max_backlog_days, etc.) |
| `scraping_priorities` | File de scraping | secteur, keyword, ville, min_emails, priorite, frequence_jours, actif |
| `planned_campaigns` | Campagnes planifiees | keyword, city, date_planifiee, statut (planned/running/done) |

---

## Dashboard Flask

### App Factory (`dashboard/app.py`)

Le serveur fait ~80 lignes. Il cree l'app Flask, enregistre les blueprints, et decouvre les modules plugins.

```python
def create_app():
    app = Flask(...)
    # Enregistre 7+ blueprints depuis dashboard/routes/
    # Decouvre et charge les modules dans modules/
    return app
```

### Blueprints (routes/)

| Blueprint | Routes | Fichier |
|-----------|--------|---------|
| `leads_bp` | `/api/leads`, `/api/lead/update`, `/api/lead/delete` | `routes/leads.py` |
| `audits_bp` | `/api/audit/launch`, `/api/audit/status`, `/api/audit/cleanup` | `routes/audits.py` |
| `emails_bp` | `/api/email/generate`, `/api/email/send`, `/api/email/approve`, `/api/email/update`, `/api/email/status` | `routes/emails.py` |
| `campaigns_bp` | `/api/campaigns`, `/api/planning/*`, `/api/scraping-priorities/*`, `/api/auto-plan/*` | `routes/campaigns.py` |
| `stats_bp` | `/api/stats`, `/api/stats/funnel`, `/api/stats/niche`, `/api/stats/export`, `/api/stats/ab_test` | `routes/stats.py` |
| `review_bp` | `/review` | `routes/review.py` |
| `pages_bp` | `/` (sert dashboard-v4.html) | `routes/pages.py` |

### Pipeline (`dashboard/pipeline/`)

Le pipeline de prospection est decoupe en 7 modules :

| Module | Role | Fonction principale |
|--------|------|---------------------|
| `lead_selection.py` | Selection des leads pour un batch | `get_leads_for_pipeline()`, `_get_leads_for_batch()` |
| `email_generation.py` | Generation email (copywriter + builder) | `generate_email_for_lead(lead_id)` |
| `report_publishing.py` | Publication rapports GitHub Pages | `_publish_reports(lead_ids)` |
| `batch_management.py` | Orchestrateur principal | `maintain_batch_slots()` |
| `approval.py` | Validation Telegram + auto-approbation 5h | `notify_new_audits()`, `auto_approve_after_timeout()` |
| `notifications.py` | Notifications Telegram des batches | `_notify_and_watch_batch()` |
| `scraper_loop.py` | Scraping en arriere-plan | `background_scraper_loop()`, `start_background_scraper()` |

**Orchestration principale** (`maintain_batch_slots`) :
```
Toutes les 15 min :
  1. reconcile_batches()     -> marque les batches envoyes
  2. Calcule pending/queued  -> cible 4 batches (2 pending + 2 queued)
  3. create_batch()          -> cree les batches manquants
  4. push_queued_batches()   -> pousse queued -> pending quand quota dispo
```

---

## Planning automatique

| Heure | Action | Module |
|-------|--------|--------|
| 07h45 | Auto-planner : planifie les campagnes du jour | `auto_planner.py` |
| 08h00 | Lance les scrapings planifies | `scheduler.py` |
| Toutes les 15min | `maintain_batch_slots()` : cree/pousse les batches | `pipeline/batch_management.py` |
| Toutes les 30min | Notifie Telegram des emails prets | `pipeline/approval.py` |
| Toutes les 1h | Auto-approuve les emails apres 5h | `pipeline/approval.py` |
| 10h00 / 14h00 | Batches envoyes (pics B2B) | Resend (scheduled) |
| Continu | Boucle scraping si < 100 leads disponibles | `pipeline/scraper_loop.py` |

**Regulation backlog :**
- `backlog_days = leads_with_email / daily_quota`
- >= 3 jours : pause scraping
- 2-3 jours : 1 campagne/jour
- < 2 jours : 3 campagnes/jour

---

## Email : Templates et profils

### Situations detectees (copywriter/main.py)

| Situation | Condition | Profil | Template |
|-----------|-----------|--------|----------|
| S1 Site lent | `lcp_ms > 3000` ou `mobile_score < 65` | B | `template_profil_b.html` |
| S2 Pas de meta | Meta description absente | D | `template_profil_d.html` |
| S3 Peu d'avis | `reviews < 30` | C | `template_profil_c.html` |
| S4 Pas de site | Pas de site web | A | `template_profil_a.html` |
| S5 Note faible | `rating < 4.0` | C | `template_profil_c.html` |
| S6 Pas de CTA | Pas de tel + pas de bouton contact | B | `template_profil_b.html` |
| S7 Vieux CMS | Wix/Jimdo/Weebly detecte | B | `template_profil_b.html` |
| S8 Bon GMB + site lent | `rating >= 4.3` et `reviews >= 30` et `lcp_ms > 3000` | B | `template_profil_b.html` |

### Contenu d'un email envoye

- **Sujet** : Extrait du `<title>` du template HTML (ex: "Votre site met 3.5s a charger sur mobile")
- **Corps** : 3-4 paragraphes personnalises + screenshot du site + lien vers rapport
- **Rapport** : Page HTML interactive sur `audit.incidenx.com` avec scores, jauges, checklist SEO
- **CTA** : Lien Calendly (15 min)
- **Signature** : Jean-Marc DANSI

### Envoi

| Service | Role | Quota |
|---------|------|-------|
| Resend | Envoi principal + scheduling | 100/jour/compte |
| Brevo | Fallback | Selon plan |

Les emails sont schedules en batches de 50 sur Resend a 10h et 14h.

---

## Tracking email

**Double systeme :**

1. **Webhook Resend** (`/api/webhooks/resend`) - Temps reel
2. **Polling API Resend** (`workers/resend_polling_service.py`) - Fallback toutes les minutes

**Evenements suivis :** sent, opened, clicked, bounced, complained

**Tables mises a jour :** `email_events` (log complet) + `emails_envoyes` (champs ouvert, clique, bounce, nb_ouvertures)

---

## Systeme de plugins (modules/)

Les nouveaux modules s'ajoutent dans `modules/` et sont decouverts automatiquement au demarrage.

### Structure d'un module

```
modules/
  mon_module/
    __init__.py       # Appelle register_schema() + PipelineRegistry.register()
    pipeline.py       # Logique metier du pipeline
    database/
      tables.py       # Nouvelles tables via register_schema()
```

### Enregistrement

```python
# modules/mon_module/__init__.py
from database.schema import register_schema
from core.pipeline_registry import PipelineRegistry

# 1. Creer les tables
register_schema("Mon Module", "CREATE TABLE IF NOT EXISTS ...")

# 2. Enregistrer le pipeline
PipelineRegistry.register("mon_pipeline", ma_fonction, interval_hours=1)
```

Le module est charge automatiquement par `create_app()` dans `dashboard/app.py` via `_discover_modules()`.

### Module existant : `review_machine` (stub)

Stub fonctionnel qui demontre le pattern. Cree la table `review_machine_runs` et enregistre un pipeline "Review Collector".

---

## Configuration

### Fichier `.env`

```env
RESEND_API_KEY=re_xxxxx
BREVO_API_KEY=xkeysib-xxxxx
RESEND_WEBHOOK_SECRET=whsec_xxxxx
FROM_EMAIL=contact@mydomain.com
FROM_NAME=Jean-Marc DANSI
DB_PATH=data/prospection.db
HUB_TELEGRAM_PATH=D:/hub_telegram
AUDIT_DOMAIN=audit.incidenx.com
```

Le `.env` est charge une seule fois par `core/config.py`. Aucun module n'appelle `load_dotenv()` directement.

### Autostart Windows

- `run_dashboard.vbs` -> Flask en arriere-plan (dossier Startup)
- `D:/hub_telegram/run_bot.vbs` -> Telegram bot en arriere-plan

---

## Demarrage rapide

```bash
# 1. Installation
pip install -r requirements.txt
playwright install chromium

# 2. Configuration
cp .env.example .env
# Remplir les cles API

# 3. Lancer
python dashboard/app.py
# -> http://localhost:5001
# -> Scheduler demarre automatiquement
# -> Modules plugins charges automatiquement
```

---

## Troubleshooting

| Probleme | Solution |
|----------|----------|
| Webhook Resend ne recoit rien | Verifier tunnel Cloudflare + cle `RESEND_WEBHOOK_SECRET` dans `.env` |
| Database locked | Attendre quelques secondes (WAL mode) ou redemarrer Flask |
| Import error apres refactoring | Utiliser `from database import X` ou `from database.leads import X` |
| Module plugin non charge | Verifier `__init__.py` present + pas d'erreur dans `errors.log` |
| Emails sans message_id | Verifier `RESEND_API_KEY` dans `.env` |

---

## Historique

| Version | Date | Changements |
|---------|------|------------|
| 2.0 | 2026-04-04 | Architecture modulaire : db split, blueprints, pipeline decoupe, systeme plugins |
| 1.0 | 2026-04-04 | Webhook Resend + polling fallback |
| 0.9 | 2026-03-30 | Systeme Brevo initial |
| 0.8 | 2026-03-15 | Dashboard v4 + campaigns |
