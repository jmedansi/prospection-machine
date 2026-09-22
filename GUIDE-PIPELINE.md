# GUIDE PIPELINE — Prospection Machine

> **Complément au guide dashboard** (`/guide` → `dashboard/static/guide.html`).
> Ce document décrit la **chaîne de traitement complète** d'un prospect, du scraping
> jusqu'à l'envoi réel, et sert de **contrat de travail** pour les agents IA.
> Il traite les **DEUX objectifs** : `web` (refonte / présence web) et `general`
> (email général, sans sujet web).
>
> **Note de travail (impérative)** : avant de lancer une étape, lire dans l'ordre :
> `README.md` → les skills `.claude/skills/*/SKILL.md` (selon la phase, cf. tableau
> section  Middel) → ce guide-ci pour la partie opérationnelle. Ne jamais deviner.

---

## Table des matières

1. Vue d'ensemble — le pipeline en une image
2. La colonne vertébrale : Campagne → Liste → Prospect
3. Étape 1 — Scraping (objectifs `web` / `general`)
4. Étape 2 — Enrichissement (email, CEO, mentions légales)
5. Étape 3 — Compréhension & récap d'activité (IA)
6. Étape 4 — Rédaction de l'email & des séquences
7. Étape 5 — Validation & envoi (Telegram, rejet, relances)
8. Notes de travail de l'agent — par objectif
9. Commandes de référence (copier-coller)
10. Pièges classiques & vérifications

---

## 1. Vue d'ensemble — le pipeline en une image

```
┌──────────┐   ┌────────────┐   ┌──────────────┐   ┌──────────────┐   ┌───────────┐
│ SCRAPING │ → │ ENRICHIR   │ → │ COMPRENDRE   │ → │ RÉDIGER       │ → │ ENVOYER   │
│ maps     │   │ email /    │   │ l'activité   │   │ email +       │   │ validation│
│ ads      │   │ CEO / ment.│   │ (récap IA)   │   │ séquences     │   │ Telegram  │
└──────────┘   └────────────┘   └──────────────┘   └──────────────┘   └───────────┘
     │               │                │                  │                 │
   leads_bruts   leads_audites    leads_audites       email_obj/         emails_envoyes
   (statut       (enrichissement   phrase_synthese    corps (HTML        + prospects
   'scrape')     score obsolesc.)  diagnostic         template)          statut machine
```

**Flux de données canonique** (défini dans `AGENTS.md`) :

```
planned_campaigns
  → scraper/main.py          → leads_bruts      (statut='scrape')
  → enrichisseur/*           → leads_audites    (audit_json, problemes, phrase_synthese)
  → copywriter/main.py       → leads_audites    (diagnostic, service_propose)
  → dashboard/pipeline.py    → leads_audites    (email_objet, email_corps via email_builder)
  → validation Telegram      → leads_audites    (approuve=1)
  → envoi/resend_sender.py   → emails_envoyes   + prospects.statut
```

---

## 2. La colonne vertébrale : Campagne → Liste → Prospect

**Modèle v2 = la cible. Le modèle V5 (legacy) est décommissionné.**

- **Campagne** (ex-« objectif ») : unité porteuse du cycle de vie.
  Valeurs d'**objectif** : `web` | `general` (colonne `objectif` de la liste,
  défaut `general`). C'est un **rattachement d'ingestion**, pas un type de pipeline.
- **Liste** : l'unité opérationnelle — 1 scraping / 1 import / 1 secteur.
- **Prospect** : le lead, rattaché à UNE liste. **Règle dorée : un prospect n'existe
  pas sans campagne ni sans liste.** Aucun prospect orphelin.
- Point d'entrée unique : `core/objectif_registry.py` → `resolve_or_create_campagne()`
  (alias `resolve_or_create_objectif()`) → `get_or_create_liste()` → `import_lead_as_prospect()`.

> ⚠️ **Agent :** toujours passer par `resolve_or_create_campagne()` / `get_or_create_liste()`
> pour ingérer. Ne jamais insérer directement dans `prospects` sans `liste_id`.

---

## 3. Étape 1 — Scraping (objectifs `web` / `general`)

Scraper principal : **`scraper/main.py`** (Playwright headless, Google Maps).
Entrée : `--keyword` (métier) + `--city` + `--objectif` (campagne) + `--liste`.

### 3.1 Arguments les plus utiles (CLI réelle)

| Argument | Rôle |
|---|---|
| `--keyword` | Métier recherché (ex : `restaurant`) — **requis** |
| `--city` | Ville (ex : `Cotonou`) — **requis** |
| `--limit` | Nombre max de résultats (défaut 20) |
| `--objectif` | **Campagne v2** (nom ou id) dans laquelle ranger les leads (ex `"Refonte site web"`). Ancien terme `--campaign-id` → ID campagne |
| `--liste` | Liste cible (nom ou id) DANS la campagne ; défaut = liste par défaut |
| `--secteur` | Étiquette secteur (ex : `immobilier`) |
| `--country` | Code pays (`fr`, `bj`, `be`, `ch`, `lu`) — défaut `fr` |
| `--max-passes` | Nombre max de passes de zones (défaut 30) |
| `--min-emails` | Nombre minimum de leads avec email requis (s'arrête quand atteint) |
| `--require-contact` | Ne garder que les leads avec téléphone OU email |
| `--site-filter` | `all` / `with_site` / `without_site` (leads sans site = cibles `general`) |
| `--min-reviews` | Nombre minimum d'avis requis |
| `--multi-zone` | Agent de zones LLM pour couvrir plusieurs zones |
| `--keyword-variants` | Générer des variantes de mots-clés via LLM |

**Exemples réels :**

```bash
# Objectif web (refonte) — uniquement les établissements sans site
python scraper/main.py --keyword "restaurant" --city "Cotonou" --limit 30 \
  --objectif "Refonte site web" --country bj --site-filter without_site

# Objectif general (email seul) — avec site mais besoin de contact
python scraper/main.py --keyword "clinique esthétique" --city "Cotonou" --limit 30 \
  --objectif "Prospection générale" --country bj --require-contact --min-emails 10
```

### 3.2 Ce que produit le scraping

Chaque résultat devient un **lead brut** (`leads_bruts`, statut `scrape`) avec :
`nom`, `adresse`, `ville`, `secteur`, `site_web`, `telephone`, `email`, `rating`,
`nb_avis`, `latitude/longitude`, `note agent` (zones). Si `--objectif` est fourni,
le lead est aussi **enrichi et inséré** comme prospect v2 (miroir) via
`import_lead_as_prospect()`.

**Sniper (leads d'annonces / FB Business Ads)** : `scraper/sniper/` gère le scraping
des annonces génériques (`test_ads.py --keyword ... --country ...`, `ads_catchup.py`,
`overnight_ads_pipeline.py`). Ces leads sont injectés via `inject_leads.py` /
`inject_courtage.py`.

---

## 4. Étape 2 — Enrichissement

Les enrichisseurs tournent sur `leads_bruts` dont le statut passe en **enrichissement**,
puis mènent au résultat dans `leads_audites` (audit_json + notes). Trois axes, chaînés :

### 4.1 Emails — `scraper/email_finder.py` (email_finder_agent)

Cherche les emails sur le site du prospect, par **priorité** :
1. **Multi-pages** du site (contact, mentions légales, etc.)
2. **Patterns d'emails cachés** (anti-spam : `atob()`, entités HTML, `mailto:`)
3. **SMTP guess** (validation domaine MX via `dns.resolver`)
4. **Recherche basic homepage** (fallback)

Point d'entrée : `email_finder_agent` (le « métier email »). Ne crée jamais de leads,
il ne fait qu'enrichir.

### 4.2 CEO / dirigeant — `enrichisseur/ceo_finder.py`

- `find_ceo_ollama(url, domain)` : déduction du dirigeant via **Ollama** local
  (`get_ollama_model()` priorise llama3.2 / llama3 / mistral / qwen / phi).
  Vérifie la disponibilité d'Ollama (`localhost:11434`) ; retourne `(None, None)`
  silencieusement si injoignable (non bloquant).
- `find_ceo_legal_mentions(html)` + `find_ceo_from_url(url)` : extraction depuis les
  mentions légales + enrichissement LLM (`structure_ml_notes →
  extract_responsables_ml`).

### 4.3 Mentions légales — `enrichisseur/mentions_legales_enricher.py`

Scrape la page « mentions légales » et extrait : nom du dirigeant / responsable de
publication, email(s), téléphone(s). Écrit le résultat dans `leads_bruts.notes` +
met à jour les champs dédiés. Filtres : `source='ads'` → tous ; `source='maps'` →
`nb_avis > 50` ; `notes vide` → pas déjà traité.

**Passe ML** (`enrichisseur/extract_responsables_ml.py --test N --secteurs ...`) :
utilise la structure ML pour `structure_ml_notes` et stocke dans `ml_contacts`.

> ⚠️ **Agent :** enrichissement = données factuelles du site UNIQUEMENT. Ne jamais
> inventer un email/CEO qui n'est pas sur le site. Si rien de trouvé → champ vide (NULL),
> pas de placeholder.

---

## 5. Étape 3 — Compréhension & récap d'activité (IA)

C'est le cœur du travail IA : **comprendre ce que fait réellement le prospect** pour
adapter l'email. Résultat dans les colonnes IA de `leads_audites` :

| Colonne | Contenu |
|---|---|
| `Opportunite` | Ce que le prospect gagnerait (web : une refonte ; general : la valeur du service) |
| `Signaux` | Ce qui justifie l'opportunité (pas de site / pas de contact / score d'obsolescence…) |
| `Reco` | Recommandation (`a_verifier` / `a_contacter` / `a_contacter_prioritaire`…) |
| `Score` | Score de l'opportunité (ex : 0–5) |
| `phrase_synthese` | Récap court de l'activité du prospect (l'essentiel en une phrase) |
| `diagnostic` | Analyse détaillée site / présence web / contacts |

**Méthode (objectif `web` surtout)** : analyse du site réel (ou à défaut Google
Business / Mentions légales / WebArchive). Le scoring d'obsolescence (0-100) évalue :
pas de site / site daté / CMS vieillot (Wix, Jimdo) / pas de mentions légales /
site lent sur mobile. Ces signaux nourrissent `phrase_synthese` + `diagnostic` +
`service_propose`.

> ⚠️ **Agent :** la compréhension doit être basée sur la **vérité observée** (site,
> mentions légales, avis, BODACC). Interdiction d'inventer un secteur ou une activité.
> Utiliser les skills `audit-web`, `ia-prospection`, `qualify-leads` (scoring) +
> `refonte-extraction` (vraie maquette du client) pour les objectifs `web`.

---

## 6. Étape 4 — Rédaction de l'email & des séquences

### 6.1 Qui génère l'email — UNIQUE source de vérité

`envoi/email_builder.py → build_premium_email(lead_data, verify_link=False)`
- Templates HTML : `templates/emails/template_profil_{a,b,c,d}.html`
- Retourne un HTML complet dont le `<title>` contient l'**objet** (jamais écrit à la main).
- `envoi/email_shell.py → build_html_email` : coquille HTML propre (paragraphes, liens,
  signature) — **pas de Brute**. Le container `white-space: pre-wrap` préserve retours
  ligne / indentation du template (le template contrôle la mise en page).

**Pipeline de génération** : `dashboard/pipeline.py → generate_email_for_lead(lead_id)`
→ `copywriter/main.py → generate_email_content(audit_dict, main_problem)` → mappe
`phrase_synthese` → profil A/B/C/D → `build_premium_email()` → `email_builder` extrait
l'objet du `<title>` → sauvegarde `email_objet` + `email_corps` dans `leads_audites`.

### 6.2 Les 2 objectifs

| Objectif | Logique rédactionnelle | Exemple d'objet (`<title>` template) |
|---|---|---|
| `web` | Refonte de site : signaler un site absent/daté + proposer la maquette | `{NOM} met {LCP}s à charger sur mobile` ; `{NOM} est invisible sur Google` |
| `general` | Email général : présente la valeur du service sans angle web | `{NOM} · {RATING}/5 et {REVIEWS} avis — vos concurrents sont loin devant` |

Les **sujets ne s'écrivent JAMAIS manuellement** : ils proviennent des `<title>` des
templates (`template_profil_{a,b,c,d}.html`).

### 6.3 Séquences de relance — `envoi/sequence_engine.py`

- **Cœur v2** : `sequence_templates` (template_registry) avec positions `0..3`
  (position 0 = initial, puis relances), délais en jours, `campagne_id` (dédié)
  ou NULL (générique, fallback).
- `plan_sequences_for_lead()` planifie les relances après l'initial (statut
  `en_sequence` → event `initial`).
- **Relances** : `sequence_worker` (10h30 + toutes les heures) génère la relance
  (conditions : pas de réponse, pas de clic) → `email_objet`/`email_corps` → v2
  `pending_approval` → validation Telegram → envoi via `approve_and_send()`.
- Planning par défaut : relance_1 à J+3, relance_2 à J+7 (si ouvert sans clic),
  relance_special J+14 (chaud/tiède). `max_touches` → statut `sans_reponse` (cycle
  fermé).

---

## 7. Étape 5 — Validation & envoi

- **Validation Telegram obligatoire** (`validation_telegram=1`) : contenu stocké →
  demande ✅/❌ (callback `v2_approve_{prospect_id}`) → `approve_and_send_initial()`.
  Rien n'est envoyé sans approbation.
- `campaign_tracker` : `send_initial()` fait **UN envoi** (ou UNE demande), atomique,
  avec verrous (statut, écarté, opposition, email) → `en_sequence` + event `initial`.
- **Sélection boîte** : `apply_mailbox_selection` → pool par campagne (Resend) ou SMTP ;
  quota journalier (`usage_jour`), rotation ; **reset quotidien** (`reset_daily_quotas`).
- **Relances** : `send_relance()` via tunnel complet (validation + humanisation +
  `sequence_engine` transition relance_k → relance_{k+1}).
- Réponses entrantes : `envoi/reply_poller.py` (IMAP) → ¹NDR ¹auto_reply ¹reponse ;
  une réponse suspend les relances, un clic les arrête (machine à états).

---

## 8. Notes de travail de l'agent — par objectif

### Objectif `web` (refonte de site)

1. **Comprendre l'état réel du site** avant de proposer. Utiliser `audit-web` +
   `refonte-extraction` (site réel → couleurs/images/textes réels). Si pas de site,
   utiliser Google Business / Instagram / WebArchive / Mentions légales comme vérité.
2. **Score d'obsolescence** (0-100) : jamais deviné — basé sur signaux objectifs
   (pas de site, site daté, CMS vieillot, pas de mentions légales, site lent mobile).
3. Mappage `phrase_synthese → profil A/B/C/D` : pas de site/site daté → B ;
   pas de mentions légales → D ; note faible/peu d'avis → C ; pas de site → A.
4. Ajouter la **maquette** (`refonte-build` → `PROMPT/<IdLead>/index.html` +
   `capture.png`) quand l'opportunité le justifie.
5. **Expéditeur Resend** (`resend_sender.py`) + **humanisation** :
   `humanize=True` par défaut, `dry_run` jamais vers le LLM.

### Objectif `general` (email sans angle web)

1. Récap d'activité neutre : `phrase_synthese` décrit l'activité sans présupposé web.
2. Prioriser le secteur / la ville / le score pour adapter l'email, pas l'angle refonte.
3. Contrôler `email_valide` : uniquement de vrais emails (regex
   `/^[^\s@]+@[^\s@]+\.[^\s@]+$/`). Si l'email trouvé est un placeholder/agence
   (`contact@oswald-orb.fr`, `developer@udevweb.co`, `agence@virtuosa.fr`,
   `contact@joinoko.com`, `privacy@waze.com`, `support@waze.com`,
   `xxx@xxx.com`, `utilisateur@domaine.com`) → chercher le vrai email ou mettre à NULL.
4. **Ne jamais** envoyer sans passer par le tunnel d'approbation Telegram.

### Pour les DEUX objectifs (règles communes)

- Ne pas étendre le pipeline V5 (legacy) ; tout passe par la version v2.
- Ne pas modifier la machine à états en dehors de `core/state_machine.py`.
- Avant l'envoi : `email_objet` + `email_corps` doivent exister (générés par
  `email_builder`, pas à la main).
- Un lead ne change d'état que via `transition_prospect()` (ou `approve_and_send` /
  `send_initial` du tracker), jamais par UPDATE direct.

---

## 9. Commandes de référence (copier-coller)

```bash
# Scraping — objectif web (refonte), sans site
python scraper/main.py --keyword "restaurant" --city "Cotonou" --limit 30 \
  --objectif "Refonte site web" --country bj --site-filter without_site

# Scraping — objectif general, avec emails requis
python scraper/main.py --keyword "clinique esthétique" --city "Cotonou" --limit 30 \
  --objectif "Prospection générale" --country bj --require-contact --min-emails 10

# Enrichissement emails (site web du prospect)
python -m  (utiliser l'agent email_finder via le dashboard / worker)

# Enrichissement mentions légales (limité / par secteur)
python enrichisseur/mentions_legales_enricher.py --test 10
python enrichisseur/extract_responsables_ml.py --test 10 --secteurs "restaurant"

# Génération des emails (toute la chaîne) — via le dashboard
#  → POST /api/emails/generate  (worker v2)

# Lancer l'app (dashboard + scheduler + workers)
python app.py
```

---

## 10. Pièges classiques & vérifications

| Piège | Correction |
|---|---|
| Objet d'email écrit à la main | L'extraire du `<title>` HTML de `build_premium_email()` |
| Email non validé envoyé | Vérifier `email_valide` avant envoi ; ne pas envoyer de placeholder |
| Prospect sans `liste_id` | Toujours passer par `get_or_create_liste()` |
| Envoi sans validation Telegram | Ne jamais court-circuiter `approve_and_send()` |
| Relance hors planning | Respecter `delai_jours` + conditions (pas de réponse / pas de clic) |
| Quota bloqué (usage_jour=50/50) | `reset_daily_quotas()` au démarrage du scheduler |
| Fichier de config | `.env` : `RESEND_API_KEY`, `BREVO_API_KEY`, `GROQ_API_KEY`, `TELEGRAM_*` |
| Erreur OpenAI/Groq | Fallback automatique → modèle local (Ollama) dans `ceo_finder` |
| Boîte Resend épuisée | Ajouter une boîte Resend ou basculer sur SMTP dans `mailboxes` |
| Leads sans email dans `general` | `--require-contact` au scraping, ou enrichir via mentions légales |

---

*Dernière mise à jour : 2026-09-22. À maintenir en synchronisation avec `AGENTS.md`
(contrat canonique) — toute modification du pipeline email doit être reportée ici.*
