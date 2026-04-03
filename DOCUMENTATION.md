# 📚 Prospection Machine - Documentation Complète

**Version actuelle:** Avec webhook Resend + polling fallback  
**Date:** 2026-04-04  
**Statut:** Production-ready avec tracking email

---

## 🎯 Vue d'ensemble

Prospection Machine est un système automatisé complet de **scraping + audit + copywriting + envoi + tracking** pour générer des prospects qualifiés.

**Pipeline complet:**
```
Google Maps Scraping → Lead Enrichissement → Audit Technique → AI Copywriting → Envoi Email → Tracking Ouvertures/Clics
```

### Composants principaux

| Module | Rôle | Port | Commande |
|--------|------|------|----------|
| **Dashboard** | Interface web (cockpit) | 5001 | `python dashboard/app.py` |
| **Scraper** | Scraping Google Maps + extraction emails | - | `python scraper/main.py` |
| **Auditeur** | Audit technique (PageSpeed, SEO, Google Business) | - | `python auditeur/main.py` |
| **Copywriter** | Rédaction email IA personnalisée | - | `python copywriter/main.py` |
| **Envoi** | Envoi via Resend + Brevo | - | Intégré au dashboard |
| **Webhook Resend** | Tracking événements email (ouverture, clic, bounce) | 5001 | Endpoint Flask |
| **Polling Service** | Fallback pour récupérer événements API Resend | - | `python -m workers.resend_polling_service` |

---

## 🖥️ Dashboard Web (Port 5001)

**URL:** `http://localhost:5001`  
**Technologie:** Flask + SQLite + JavaScript moderne  
**HTML:** `dashboard/dashboard-v4.html`

### Modules Dashboard

#### 1. **Leads** (`/api/leads`)
Tableau principal des prospects.

**Filtres disponibles:**
- `statut`: tous, nouveau, audit_en_cours, audit_ok, email_sent, bounced
- `site`: tous, avec, sans (a un site web ou pas)
- `email`: tous, avec, sans (a une email ou pas)
- `note`: tous, bons (≥4), mauvais (<4)
- `sector`: filtrer par catégorie
- `page`: pagination (défaut: 1)
- `limit`: résultats par page (défaut: 50)

**Réponse JSON:**
```json
{
  "leads": [{
    "id": 123,
    "nom": "Restaurant XYZ",
    "ville": "Paris",
    "secteur": "Restauration",
    "note": 4.5,
    "avis": 150,
    "site_web": "https://restaurant.fr",
    "email": "contact@restaurant.fr",
    "statut": "email_sent",
    "score_urgence": 8.5,
    "a_site": true,
    "a_email": true
  }],
  "page": 1,
  "total_pages": 10,
  "total": 500
}
```

---

#### 2. **Statistiques** (`/api/stats`)
Métriques globales du système.

**Réponse:**
```json
{
  "total_leads": 5000,
  "leads_by_status": {
    "nouveau": 1000,
    "audit_ok": 2000,
    "email_sent": 1500,
    "bounced": 500
  },
  "emails_sent": 1500,
  "emails_opened": 450,
  "open_rate": 0.30,
  "click_rate": 0.12
}
```

---

#### 3. **Campagnes** (`/api/campaigns`)
Gestion des campagnes d'envoi (groupe de leads avec date, secteur, etc.)

**GET /api/campaigns**
```json
{
  "campaigns": [{
    "id": 1,
    "nom": "Restaurants Paris 2026-04-04",
    "date": "2026-04-04",
    "secteur": "Restauration",
    "leads_count": 150,
    "sent": 120,
    "opened": 45,
    "clicked": 15
  }]
}
```

**POST /api/campaigns** - Créer une campagne
```json
{
  "nom": "Restaurants Paris",
  "secteur": "Restauration",
  "lead_names": ["Rest A", "Rest B"],
  "template": "template_profil_a"
}
```

**DELETE /api/campaigns/:id** - Supprimer une campagne

---

#### 4. **Audits** (`/api/audit/*`)

**POST /api/audit/launch**
Lance l'audit pour un lead (PageSpeed, SEO, données Google Business).

**Paramètres:**
```json
{
  "lead_id": 123,
  "recheck": false
}
```

**GET /api/audit/status**
État des audits en cours/terminés.

**POST /api/audit/cleanup**
Nettoie les audits échoués/orphelins.

---

#### 5. **Emails** (`/api/email/*`)

**POST /api/email/generate**
Génère un brouillon d'email pour un lead (via Copywriter IA).

**Paramètres:**
```json
{
  "lead_id": 123,
  "audit_id": 456
}
```

**POST /api/email/approve**
Valide et enregistre l'email brouillon.

**PUT /api/email/update**
Met à jour le contenu d'un email.

**POST /api/email/send**
Envoie l'email via Resend.

**Paramètres:**
```json
{
  "email_record_id": 789,
  "lead_id": 123
}
```

**GET /api/email/status**
Statut des envois (en attente, envoyé, ouvert, cliqué, bounced).

---

#### 6. **Planning / Séquences** (`/api/planning`)

Gestion des plans de suivi automatique (relances).

**GET /api/planning**
Liste des séquences planifiées.

**POST /api/planning**
Créer une séquence de relance.

**DELETE /api/planning/:id**
Supprimer une séquence.

**POST /api/planning/:id/launch**
Lancer immédiatement une séquence.

**GET /api/planning/quota**
Quota restant (combien d'emails peuvent être envoyés).

**POST /api/planning/quota**
Mettre à jour le quota.

---

#### 7. **Scraping** (`/api/scraping-priorities`, `/api/scraper/fill-quota`)

Gestion des files de scraping.

**GET /api/scraping-priorities**
Priorités actuelles.

**POST /api/scraping-priorities**
Ajouter une priorité (niche + ville).

**POST /api/scraping-priorities/:id/toggle**
Activer/désactiver une priorité.

**POST /api/scraper/fill-quota**
Remplir le quota de leads à scraper.

---

#### 8. **Webhooks Email Tracking** (`/webhooks/resend`, `/prospection/webhooks/resend`)

**Événements suivis:**
- `email.sent` - Email delivré avec succès
- `email.opened` - Email ouvert
- `email.clicked` - Lien cliqué
- `email.bounced` - Email non-délivrable
- `email.complained` - Plainte spam

**Données stockées:**
- `email_events` table - Tous les événements avec timestamp
- `emails_envoyes` - Mise à jour des champs:
  - `ouvert` (booléen)
  - `nb_ouvertures` (compteur)
  - `date_ouverture` (timestamp)
  - `clique` (booléen)
  - `date_clic` (timestamp)
  - `bounce` (booléen)
  - `statut_envoi`

**GET /api/webhook-debug**
Vérifier les derniers événements reçus (dernier 50).

**Réponse:**
```json
{
  "recent_events": [{
    "event_type": "opened",
    "timestamp": "2026-04-04T10:30:00Z",
    "email_record_id": 789,
    "email_destinataire": "contact@restaurant.fr"
  }],
  "stats": {
    "sent": 100,
    "opened": 45,
    "clicked": 15,
    "bounced": 5
  }
}
```

---

#### 9. **Auto-Planning** (`/api/auto-plan`)

Planification automatique de campagnes basées sur les niches.

**GET /api/auto-plan/backlog**
Backlog des campagnes prêtes à lancer.

**POST /api/auto-plan/now**
Lancer une campagne immédiatement.

---

#### 10. **Bounce Check** (`/api/bounces/check`)

Vérifier et récupérer les emails bounced depuis Resend/Brevo.

---

#### 11. **Analytics** (`/api/stats/*`)

**GET /api/stats/funnel**
Conversion funnel (leads → audit → email → ouverture → clic).

**GET /api/stats/niche**
Statistiques par niche/secteur.

**GET /api/stats/export**
Exporter les statistiques en CSV/JSON.

**GET /api/stats/ab_test**
Résultats des tests A/B (si activés).

---

#### 12. **Config** (`/api/config`, `/api/settings/identity`)

**GET /api/config**
Configuration actuelle du système.

**POST /api/settings/identity**
Mettre à jour l'identité (nom, email d'envoi, signature).

---

## 📡 Modules Core

### 1. **Scraper** (`scraper/main.py`)

**Rôle:** Scraping Google Maps + extraction d'emails/téléphones.

**Commande:**
```bash
python scraper/main.py --keyword "restaurant" --city "Paris" --limit 10
```

**Paramètres:**
- `--keyword`: Métier recherché
- `--city`: Ville cible
- `--limit`: Nombre max de leads
- `--dry-run`: Test sans écrire en DB

**Données extraites par lead:**
- Nom, adresse, téléphone
- URL Google Maps
- Email (si trouvé)
- Note (rating), nb avis
- Site web (si trouvé)
- Catégorie/secteur
- Coordonnées GPS

**Stockage:** `emails_bruts` table SQLite

---

### 2. **Auditeur** (`auditeur/main.py`)

**Rôle:** Analyse technique des sites web.

**Audits effectués:**
- **PageSpeed Insights** (Google) - Performance mobile/desktop, Core Web Vitals
- **SEO Basic** - Métadonnées, structure, headers
- **Google Business Profile** - Informations fiche Google

**Algorithme de détection de problèmes:**
- Vitesse (< 50 sur 100)
- SEO (title absent, métadescription vide)
- Configuration Google Business (incomplète, horaires manquants)

**Score d'urgence:** Combinaison de tous les problèmes détectés.

**Stockage:** `audits` table SQLite

---

### 3. **Copywriter / IA** (`copywriter/main.py`)

**Rôle:** Génération d'email personnalisé via Claude.

**Entrées:**
- Lead (nom, secteur, URL, téléphone)
- Résultat d'audit (problèmes détectés)

**Sortie:** Email personnalisé avec:
- Salutation
- Problème détecté (1 seul, le plus urgent)
- Proposition de valeur
- CTA (call-to-action)
- Signature

**Intégration:** Appelé via `/api/email/generate` du dashboard.

---

### 4. **Envoi Email** (`envoi/`)

#### a) **Resend Integration** (`envoi/resend_sender.py`)
Service d'envoi email via Resend API.

**Features:**
- Envoi depuis adresse configurée
- Suivi des message_id pour tracking
- Gestion des erreurs avec fallback

**Configuration:**
```
RESEND_API_KEY = "re_xxxxx"
FROM_EMAIL = "contact@mydomain.com"
```

#### b) **Brevo Integration** (`envoi/brevo_sender.py`)
Service d'envoi email via Brevo (Sendinblue).

**Features:**
- Envoi de masse
- Gestion de listes
- Suppression automatique de bounces

**Configuration:**
```
BREVO_API_KEY = "xkeysib-xxxxx"
```

#### c) **Email Tracking Service** (`envoi/email_tracking_service.py`)

Classe pour enregistrer les événements email et mettre à jour la BD.

**Méthodes:**
- `create_email_record(lead_id, email_addr, template_name)` - Crée un enregistrement
- `update_message_id(email_record_id, message_id_resend, message_id_brevo)` - Enregistre les IDs
- `mark_send_error(email_record_id, error_msg)` - Marque comme erreur
- `log_event(message_id, event_type, timestamp, meta)` - Enregistre un événement webhook
- `mark_opened(message_id, timestamp, meta)` - Marque comme ouvert
- `mark_clicked(message_id, timestamp, meta)` - Marque comme cliqué
- `mark_bounced(message_id, timestamp, meta)` - Marque comme bounced

---

### 5. **Database** (`database/db_manager.py`)

**Technologie:** SQLite3 avec context manager.

**Tables principales:**

| Table | Rôle |
|-------|------|
| `leads` | Prospects (nom, email, secteur, statut) |
| `emails_bruts` | Leads non-traités du scraper |
| `audits` | Résultats audits technique |
| `audits_rapports` | Rapports détaillés PageSpeed |
| `emails_envoyes` | Enregistrements d'envoi (message_id, statut) |
| `email_events` | Tous les événements webhook (sent, opened, clicked) |
| `crm_manual` | Notes/suivi manuel |
| `sequences_email` | Relances planifiées |
| `campaigns` | Groupes d'envoi |
| `scraping_priorities` | Files de scraping |
| `auto_plans` | Plans générés automatiquement |

**Fonctions principales:**

```python
# Leads
get_all_leads(statut, limit)
insert_lead(nom, email, ...)
update_lead(lead_id, **updates)
delete_lead(lead_id)

# Audits
insert_audit(lead_id, score, problems, ...)
get_audits_ready_for_email()
update_audit_approval(audit_id, approved)

# Emails
insert_email_sent(lead_id, email_addr, message_id, template)
update_email_tracking(message_id, {'ouvert': 1, 'date_ouverture': ...})
insert_email_event(message_id, event_type, timestamp, meta)

# Campaigns
insert_campaign(nom, date, secteur, lead_names)
get_all_campaigns()
delete_campaign(campaign_id)

# Stats
get_dashboard_stats()
```

---

## 🔧 Workers (Background Services)

### 1. **Resend Polling Service** (`workers/resend_polling_service.py`)

Récupère les événements d'email depuis l'API Resend (alternative au webhook).

**Commande:**
```bash
python -m workers.resend_polling_service
```

**Fonctionnement:**
1. Récupère tous les emails envoyés des 30 derniers jours
2. Appelle l'API Resend pour chaque email
3. Extrait les événements (opened, clicked, bounced)
4. Met à jour la BD

**Fréquence:** À exécuter chaque minute (via scheduler).

---

### 2. **Resend Polling Scheduler** (`workers/scheduler.py`)

Lance le polling service toutes les minutes.

**Commande:**
```bash
python -m workers.scheduler
```

**Exécution:**
- Boucle infinie avec schedule library
- Lance le job toutes les 60 secondes
- Vérifie toutes les 10 secondes
- Redémarre automatiquement en cas d'erreur

---

### 3. **Sequence Service** (Relances planifiées)

Lance les séquences de relance à heure planifiée.

**Fonctionnement:**
- Récupère les séquences prêtes à envoyer
- Génère/valide les emails
- Envoie via Resend/Brevo
- Met à jour les statuts

---

## 📊 Base de Données

### Schéma SQLite

#### Table `leads`
```sql
CREATE TABLE leads (
  id INTEGER PRIMARY KEY,
  nom TEXT,
  email TEXT,
  telephone TEXT,
  ville TEXT,
  secteur TEXT,
  site_web TEXT,
  google_maps_url TEXT,
  note REAL,
  nb_avis INTEGER,
  statut TEXT (nouveau|audit_en_cours|audit_ok|email_sent|bounced|interested),
  score_urgence REAL,
  date_ajout TIMESTAMP,
  date_audit TIMESTAMP,
  date_dernier_email TIMESTAMP
)
```

#### Table `emails_envoyes`
```sql
CREATE TABLE emails_envoyes (
  id INTEGER PRIMARY KEY,
  lead_id INTEGER,
  email_destinataire TEXT,
  message_id_resend TEXT UNIQUE,
  message_id_brevo TEXT UNIQUE,
  template_name TEXT,
  contenu_email TEXT,
  date_envoi TIMESTAMP,
  ouvert BOOLEAN DEFAULT 0,
  nb_ouvertures INTEGER DEFAULT 0,
  date_ouverture TIMESTAMP,
  clique BOOLEAN DEFAULT 0,
  date_clic TIMESTAMP,
  bounce BOOLEAN DEFAULT 0,
  statut_envoi TEXT,
  erreur_message TEXT
)
```

#### Table `email_events`
```sql
CREATE TABLE email_events (
  id INTEGER PRIMARY KEY,
  email_record_id INTEGER,
  lead_id INTEGER,
  event_type TEXT (sent|opened|clicked|bounced|complained),
  event_data JSON,
  timestamp TIMESTAMP
)
```

#### Table `audits`
```sql
CREATE TABLE audits (
  id INTEGER PRIMARY KEY,
  lead_id INTEGER,
  score_pagespeed INTEGER,
  score_seo INTEGER,
  problemes TEXT (JSON list),
  rapport_json JSON,
  date_audit TIMESTAMP,
  approuve BOOLEAN DEFAULT 0
)
```

---

## 🔐 Configuration & Environnement

### Fichier `.env`

```env
# API Keys
RESEND_API_KEY=re_xxxxx
BREVO_API_KEY=xkeysib-xxxxx
CLAUDE_API_KEY=sk-ant-xxxxx

# Webhooks
RESEND_WEBHOOK_SECRET=whsec_vVaIViVqGhxsY0I5+AC1i9PxGv87dPPF

# Email
FROM_EMAIL=contact@mydomain.com
FROM_NAME=Prospection Machine

# Database
DATABASE_PATH=data/prospection.db

# Google Sheets (optionnel)
GOOGLE_SHEETS_ID=xxxxx
GOOGLE_SHEET_CREDENTIALS=path/to/creds.json

# Limites
QUOTA_EMAILS_PAR_JOUR=50
QUOTA_SCRAPING_PAR_JOUR=200

# Features
ENABLE_WEBHOOK_RESEND=true
ENABLE_POLLING_RESEND=true
ENABLE_AUTO_PLANNING=true
```

---

## 🚀 Démarrage rapide

### 1. Installation
```bash
git clone https://github.com/jmedansi/prospection-machine.git
cd prospection-machine
pip install -r requirements.txt
playwright install chromium
```

### 2. Configuration
- Créer `.env` avec clés API
- Configurer base de données: `python database/db_manager.py`

### 3. Lancer le dashboard
```bash
python dashboard/app.py
# Accès: http://localhost:5001
```

### 4. (Optionnel) Lancer le polling Resend
```bash
python -m workers.scheduler
# Récupère les événements email chaque minute
```

### 5. (Optionnel) Lancer le service de relances
```bash
python -m workers.sequence_service
# Lance les séquences de relance planifiées
```

---

## 📈 Workflow Complet

### Scraping → Audit → Email → Tracking

1. **Scraping** (Manuel ou planning)
   - `POST /api/scraper/fill-quota` ou `python scraper/main.py`
   - Stocke leads bruts dans `emails_bruts`

2. **Enrichissement Lead**
   - Champs extraits: nom, email, site, téléphone, secteur

3. **Audit Technique** (Manuel ou auto)
   - `POST /api/audit/launch` pour un lead
   - Audit PageSpeed, SEO, Google Business
   - Résultat: score + liste de problèmes

4. **Copywriting IA**
   - `POST /api/email/generate` (appelle Claude)
   - Génère brouillon d'email basé sur le problème urgent

5. **Validation Email**
   - `POST /api/email/approve` (validé par utilisateur)
   - Enregistre le contenu final

6. **Envoi Email**
   - `POST /api/email/send` (via Resend/Brevo)
   - Enregistre message_id

7. **Webhook Tracking**
   - Resend webhook → `/webhooks/resend`
   - Enregistre: sent, opened, clicked, bounced
   - Met à jour `email_events` et `emails_envoyes`

8. **Analytics**
   - `GET /api/stats` - Vue d'ensemble
   - `GET /api/stats/funnel` - Conversion
   - `GET /api/stats/niche` - Par secteur

---

## 🛠️ Troubleshooting

### Webhook Resend ne reçoit pas d'événements

1. Vérifier que le tunnel Cloudflare est actif:
   ```bash
   curl https://webhook.mjautomation.shop/api/webhook-debug
   ```

2. Vérifier que la clé secrète est correcte dans `.env`

3. Test manual dans Resend Dashboard → Webhooks → "Send test event"

4. Vérifier les logs: `GET /api/webhook-debug` doit montrer les événements

### Alternative: Activer Polling Service
```bash
python -m workers.scheduler
```
Récupère les événements via API Resend chaque minute.

### Database locked
- Attendre quelques secondes (les writers vont libérer)
- Ou redémarrer le service Flask

### Emails n'ont pas de message_id
- Vérifier que les clés API Resend/Brevo sont correctes
- Vérifier les logs d'erreur dans `errors.log`

---

## 📚 Fichiers Importants

| Fichier | Rôle |
|---------|------|
| `dashboard/app.py` | Serveur Flask principal (1000+ lignes) |
| `dashboard/dashboard-v4.html` | Interface web |
| `database/db_manager.py` | Gestion SQLite |
| `scraper/main.py` | Scraping Google Maps |
| `auditeur/main.py` | Audit technique |
| `copywriter/main.py` | Génération email IA |
| `envoi/email_tracking_service.py` | Tracking email |
| `envoi/resend_sender.py` | Envoi Resend |
| `envoi/brevo_sender.py` | Envoi Brevo |
| `workers/resend_polling_service.py` | Polling API Resend |
| `workers/scheduler.py` | Scheduler polling |

---

## 📝 Notes

- **Tracking:** Webhook + Polling (fallback)
- **Emails:** Resend + Brevo (fallback)
- **IA:** Claude API pour copywriting
- **UI:** Responsive, temps réel avec fetch polling
- **DB:** SQLite = simple, pas de dépendance externe
- **Logs:** `errors.log` et console

---

## 🔄 Historique des Versions

| Version | Date | Changements |
|---------|------|------------|
| 1.0 | 2026-04-04 | Webhook Resend + polling fallback |
| 0.9 | 2026-03-30 | Système Brevo initial |
| 0.8 | 2026-03-15 | Dashboard v4 + campaigns |

---

**Dernière mise à jour:** 2026-04-04  
**Auteur:** Prospection Machine Team
