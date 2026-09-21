# AGENTS.md — Règles pour agents IA (Claude, Copilot, etc.)

Ce fichier documente l'architecture **authoritative** du pipeline d'emails.
Lire entièrement avant de modifier quoi que ce soit lié aux emails, au copywriting ou aux templates.

---

## 1. Pipeline complet — flux de données

```
planned_campaigns
    → scraper/main.py          → leads_bruts (statut='scrape')
    → auditeur/main.py         → leads_audites (audit_json, problemes)
    → copywriter/main.py       → leads_audites (phrase_synthese, diagnostic)
    → dashboard/pipeline.py    → leads_audites (email_objet, email_corps via email_builder)
    → Telegram validation      → leads_audites (approuve=1)
    → envoi/resend_sender.py   → emails_envoyes + leads_bruts.statut='envoye'
```

---

## 1bis. Le v2 — modèle piloté par objectif

> **Ce modèle EST la cible. Le pipeline 1 (legacy) est en décommissionnement** :
> ne pas étendre `leads_bruts` / `leads_audites` / `email_builder` — maintenance uniquement.

### Règle dorée
**Un prospect n'existe pas sans objectif.** L'utilisateur crée son objectif (texte libre :
« Refonte site web », « Lancement application »…) AVANT d'enregistrer tout lead.
Tout ingest (scraping Maps, CSV, JSON, IA) doit savoir dans QUEL objectif ranger les leads.

### Schéma v2 (même base `data/prospection.db`, `migrate_v2_schema()` idempotente)
- `objectifs` : `id`, `nom` (unique, libre), `objectif_principale`, `description`, `secteur`,
  `validation_telegram` (0=auto, 1=requis), `envoi_auto` (1=auto-send, 0=manuel),
  `max_touches`, `statut` (`actif` / `archive`).
- `prospects` : rattaché à `objectif_id`, `statut` = machine à états, `statut_meta` (JSON),
  `data_extra` (JSON libre : lien_maps, logo_url, email_2, campaign_id…).
- `prospect_events` : journal d'audit (`creation`, `status_change`, `desinscription`…).
- `suppression_list` : liste NOIRE GLOBALE — un email désinscrit est rejeté dans TOUT objectif.

### Point d'entrée unique de l'ingestion — `core/objectif_registry.py`
- `resolve_or_create_objectif(nom_ou_id)` → résout par id (numérique) ou par nom, crée à la volée,
  ignore les objectifs archivés. Retourne `(id, nom)` ou `None`.
- `import_lead_as_prospect(objectif_id, lead, source='scraping', data_extra_extra=None)` → mapping
  des clés enrichies (nom/email/telephone/site_web/adresse/ville/rating/nb_avis, secteur←category ;
  extra : lien_maps, logo_url, email_2, email_source, statut_email, mot_cle, pays, date_scraping)
  → `prospects_repo.insert_prospect(...)`.
- Le scraping : `scraper/main.py --objectif <nom|id>` → résolution UNE fois, insertion miroir v2
  après chaque `db_insert_lead` legacy. Le dashboard (`POST /api/scraper/launch`, body
  `v2_objectif`) et `services/scraper_runner.launch_scraper(v2_objectif=...)` font passer la valeur.

### UI globale — sélecteur d'objectif en haut (remplace « Campagne »)
- Le sélecteur d'objectif vit dans la **topbar** (`components/header.html`, `#obj-select`),
  à l'emplacement de l'ancien filtre Campagne. Il pilote TOUS les onglets :
  `objectifs.js` (`localStorage.pm_objectif_id` → `window._ul.v2ObjectifId/v2ObjectifNom`,
  exposé par `unified_leads.js` `window._ul = _ul`).
- Leads → endpoints v2 (`/api/v2/objectifs/<id>/leads…`) ; « — Archive — » = repli legacy.
- **Stats cockpit objectif-aware** : `GET /api/stats?objectif_id=<id>` →
  `database.stats._stats_v2(conn, id)` (prospects machine à états). Sans `objectif_id` :
  si les tables legacy (§1) existent encore → stats legacy ; sinon (après purge) →
  **vue v2 GLOBALE** (`_stats_v2(conn, None)` = toutes prospects de tous les objectifs).
  Audits/scores/ROI à 0 tant que le v2 n'enregistre pas ces événements.

### Machine à états — `core/state_machine.py`
- Statuts pilotés : `qualifie → en_sequence → relance_1 → relance_2` ; sorties vers
  `a_traiter_humain`, `rdv_obtenu`, `checkup`, et les refus (`deja_client`, `pas_interesse`, …).
- États FINAUX (plus aucune transition) : `rdv_obtenu`, `ne_plus_contacter`, `adresse_invalide`.
- `OVERRIDE_TRANSITIONS = {'ne_plus_contacter', 'adresse_invalide'}` : autorisées depuis N'IMPORTE
  quel état, amènent à l'état final.
- `transition_prospect(pid, nouveau, reason=...)` : SEULE voie pour changer un statut ; journalise
  un `status_change` dans `prospect_events` et remplit `statut_meta.previous_statut`.

### Désinscription (opposition) — `prospects_repo.set_ne_plus_contacter()`
- `True` : `ne_plus_contacter=1` + insert email dans `suppression_list` + event `desinscription`
  + transition machine à états → `ne_plus_contacter`.
- `False` : efface le flag + ligne `suppression_list` (réactivation).

### Tunnel d'envoi v2 — `envoi/`
- `gateway.py → envoyer(message, boîte)` : façade d'envoi UNIQUE (SMTP Zoho + Resend).
  Sélection de boîte via `get_next_mailbox(objectif_id, backend_pref)` (actif, quota jour,
  pool d'objectif, backend smtp/resend/auto, rotation usage ASC). Incrément `usage_jour`
  JAMAIS en dry_run. Table `mailboxes` épuisée non vide → None (pas de seed depuis .env).
- `template_registry.py` : templates par objectif ou génériques (`sequence_templates`,
  colonnes `objectif_id` NULL, `position`, `delai_jours`, `actif`). Dédié > générique.
  Variables autorisées : `{{prenom}} {{entreprise}} {{secteur}} {{site_web}} {{offre}}
  {{mot_cle}} {{email}}` ; `render_template` signale les variables inconnues.
- `humanize.py → humanize_email(objet, corps, prospect, dry_run)` : passe de réécriture IA
  via `config_manager.handle_llm_call` (Groq). Jamais bloquant : sans clé ou en échec,
  retour à l'original. `dry_run=True` → touche jamais le LLM.
- `sequence_engine.py → send_initial(objectif_id, prospect_id, ...)` : verrous (statut,
  écarté, opposition, email) → rendu position 0 → humanisation → envoi → transition
  `en_sequence` + event `initial` (payload, mailbox_id, message_id). Idempotent.
- **Validation Telegram** : `objectifs.validation_telegram` (0=auto, 1=requis).
  − 1 → `send_initial` rend/stocke le contenu, envoie la demande ✅/❌ (pattern
  `hub_telegram/pending.db`, callback `v2_approve_{prospect_id}`) et passe le prospect
  en attente (event `validation_requete`), aucune transition tant que pas approuvé.
  − ✅ → `approve_and_send_initial(prospect_id)` (poller `v2_approval_poll`, 1 min)
  réutilise le contenu STOCKÉ puis envoie réel. ❌ → `validation_refusee`, rien n'est envoyé.
  − 0 → envoi direct.
- **Les relances (positions > 0) et le quota global vivront dans le scheduler** :
  `send_initial` fait UN envoi (ou UNE demande), atomique.

### Orchestration des envois — `core/orchestration.py`
- Kill-switch global `planning_settings.v2_auto_send` (`'1'` par défaut, toggle « Auto »
  dans la topbar → `/api/v2/auto-send`) : coupé → l'auto-send ne tourne pas.
- `objectifs.envoi_auto` (modal « Gérer l'objectif ») : 0 = SLT manuel (le scheduler ne
  le touche pas), 1 = participe à l'auto-send.
- `run_auto_send(objectif_id=None, limit_per_objectif=10, manual=False)` :
  − mode scheduler (`objectif_id=None`) : kill-switch + `enabled_objectifs()`
    (`statut='actif'` ET `envoi_auto=1`) → chaque candidat passe par `send_initial`
    (verrous + validation Telegram + quota) ;
  − `manual=True` (bouton `POST /api/v2/objectifs/<id>/send` « ▶ Envoyer ») : bypass du
    kill-switch ET de `envoi_auto` (action explicite utilisateur).
- `candidates_for(objectif_id, limit)` : `qualifie` + non écarté + non opposé + email
  présent + absent de `suppression_list`, FIFO (created_at ASC).
- Jobs scheduler v2 :
  − `v2_send_initial` (5 min) : `run_auto_send()` ;
  − `v2_send_relances` (10 min) : `run_relances()` ;
  − `v2_reply_poll` (15 min) : `envoi.reply_poller.run_poll()` (réponses entrantes) ;
  − `v2_approval_poll` (1 min) : `approve_and_send_initial()` sur callback `v2_approve_*`.

### Relances v2 — `sequence_engine.send_relance()` / `core.orchestration.relances_due()`
- Mécanique : statut détermine la position suivante (`en_sequence→1`, `relance_1→2`,
  `relance_2→3`) ; le template position N (`delai_jours`) est dû quand
  `dernière_touche + delai_jours ≤ maintenant` ; chaque relance repasse par le tunnel
  complet (verrous, rendu, humanisation, ✅ Telegram si `validation_telegram=1`,
  transition `relance_k → relance_{k+1}`).
- `max_touches` (objectifs) : touché → transition `sans_reponse` (cycle fermé).
- **Callback Telegram partagé** `v2_approve_{prospect_id}` : `_request_validation()`
  purge le pending.db avant toute nouvelle demande (l'initial consommé ne bloque pas
  la relance suivante) ; l'event `validation_requete` stocke `step`, `from_statut`,
  `to_statut` + contenu → `approve_and_send_initial()` gère toutes les touches.
- L'UI de gestion des relances vit dans la topbar : bouton « Séquence » → modal
  `modal-obj-sequence` listant les étapes (position 0..3, objet, corps, delai_jours, actif).
  Dédié (objectif_id) vs générique (NULL) — un générique sert de secours si aucune étape
  dédiée n'existe à la même position. API : `GET/POST /api/v2/objectifs/<id>/sequence`,
  `PUT/DELETE /api/v2/sequence-templates/<template_id>` (`template_registry.update()`
  met à jour par id, champs partiels).

### Réponses entrantes — `envoi/reply_poller.py` (IMAP, job `v2_reply_poll` 15 min)
- Poll de chaque boîte `mailboxes` avec creds IMAP (`imap_host/user/pass`) : emails
  UNSEEN des dernières 48 h, marqués SEEN après traitement (idempotent).
- Classification (`classify`) : `ndr` (mailer-daemon, delivery-status, sujet
  undeliverable…) et `auto_reply` (OOO, noreply…) → event du même nom, AUCUNE
  transition. Sinon `reponse` → transition `a_traiter_humain` (règle spec §2 :
  toute réponse suspend les relances — `relances_due()` ne sélectionne plus que
  `en_sequence`/`relance_k`) + event `reponse` (from_addr, sujet, date, message_id,
  snippet, mailbox_email).
- Matching prospect : 1) `References`/`In-Reply-To` égaux à un `message_id` stocké
  en `prospect_events` (précis, Resend/SMTP avec Message-ID) ; 2) sinon adresse From
  == `prospects.email` avec statut déjà séquencé (`SENT_CLAUSE`, hors qualifie/qualifié
  écarté/ne_plus_contacter). Pas de classification automatique positive → `rdv_obtenu`
  (état FINAL) : le tri est laissé à l'humain (décision produit).
- API : `POST /api/v2/replies/poll` (poll manuel), `GET /api/v2/replies/recent`
  (derniers événements). Le vieux `sniper/imap_poller.py` reste legacy (step 1).
- File humaine : filtre « À traiter (répondu) » (`ul-filter-statut`) → sélecteur
  rapide « → Statut » par ligne (options = transitions autorisées de la machine à
  états via `GET /api/v2/statuts/transitions`) : `rdv_obtenu` / `pas_interesse` /
  `a_relancer_plus_tard` / ré-ouverture `en_sequence`/`relance_1`. Rien n'est
  auto-classé (état final `rdv_obtenu` = décision humaine).

### Interdictions (absolues)
1. Ne JAMAIS insérer un lead dans `prospects` sans `objectif_id` (pas de prospect orphelin).
2. Ne JAMAIS court-circuiter `suppression_list` : un email désinscrit est rejeté partout,
   `statut_dedupe='suppression_list'`.
3. Ne JAMAIS appeler `transition_prospect()` hors de `core/state_machine.py`.
4. Ne JAMAIS étendre le flux legacy (section 1) : il disparaîtra après backup + purge.
5. Toujours résoudre l'objectif via `resolve_or_create_objectif()` (jamais d'`INSERT` direct).

---

## 2. Génération d'emails — règles ABSOLUES

### ✅ Ce qui génère les emails HTML (UNIQUE source de vérité)

**`envoi/email_builder.py` → `build_premium_email(lead_data, verify_link=False)`**

- Utilise les templates HTML dans `templates/emails/template_profil_{a,b,c,d}.html`
- Retourne un HTML complet avec `<title>` contenant l'objet de l'email
- `email_objet` = extrait depuis `<title>` du HTML généré : `re.search(r'<title>([^<]+)</title>', html)`
- NE PAS contourner, NE PAS créer de templates alternatifs, NE PAS faire de wrapper HTML

### ✅ Ce qui détecte la situation commerciale

**`copywriter/main.py` → `generate_email_content(audit_dict, main_problem)`**

- Retourne uniquement : `phrase_synthese`, `diagnostic`, `rapport_resume`, `service_propose`
- NE génère PAS d'`email_objet` ni d'`email_corps`
- NE fait PAS d'appel LLM

### ✅ Ce qui orchestre le pipeline

**`dashboard/pipeline.py` → `generate_email_for_lead(lead_id)`**

- Appelle `generate_email_content()` → obtient `phrase_synthese`
- Mappe `phrase_synthese` → profil A/B/C/D
- Appelle `build_premium_email()` → obtient le HTML
- Extrait `email_objet` depuis `<title>` du HTML
- Sauvegarde `email_objet` + `email_corps` dans `leads_audites`

### ✅ Ce qui envoie les emails de prospection

**`envoi/resend_sender.py` → `send_prospecting_email(lead_id)`**

- Seul envoyeur autorisé pour la prospection
- Gating obligatoire : `approuve=1`

---

## 3. Mapping situation → profil email

| Situation (phrase_synthese)      | Profil | Template HTML             |
|----------------------------------|--------|---------------------------|
| Site lent sur mobile             | B      | template_profil_b.html    |
| Bon GMB, mauvais site            | B      | template_profil_b.html    |
| Pas de bouton contact / tel      | B      | template_profil_b.html    |
| CMS vieillot (Wix/Jimdo)         | B      | template_profil_b.html    |
| Pas de meta description          | D      | template_profil_d.html    |
| Peu d'avis Google                | C      | template_profil_c.html    |
| Note Google faible               | C      | template_profil_c.html    |
| Pas de site web                  | A      | template_profil_a.html    |

---

## 4. Sujets des templates (exemples réels)

- **Profil A** : `voici une ébauche gratuite de votre site web`
- **Profil B** : `{NOM} met {LCP}s à charger sur mobile`
- **Profil C** : `{NOM} · {RATING}/5 et {REVIEWS} avis — vos concurrents sont loin devant`
- **Profil D** : `{NOM} est invisible sur Google`

Ces sujets proviennent des `<title>` des templates HTML. Ne jamais les écrire manuellement.

---

## 5. Ce qui est MORT — ne pas utiliser

| Fichier / Fonction                                    | Statut   | Remplacé par                     |
|-------------------------------------------------------|----------|----------------------------------|
| `auditeur/agents/business_copywriter.py`              | MORT     | `envoi/email_builder.py`         |
| `envoi/brevo_sender.send_prospecting_email()`         | MORT     | `envoi/resend_sender.py`         |
| Tout champ `email_objet` / `email_corps` dans `SITUATIONS_TEMPLATES` (copywriter) | SUPPRIMÉ | Extrait du `<title>` HTML |

`envoi/brevo_sender.send_email()` reste actif pour les **alertes internes uniquement**.

---

## 6. Règles pour les agents IA

1. **Ne jamais créer de template HTML inline** pour les emails de prospection. Toujours utiliser `build_premium_email()`.
2. **Ne jamais écrire l'objet de l'email manuellement**. L'extraire depuis `<title>` du HTML généré.
3. **Ne jamais appeler `brevo_sender.send_prospecting_email()`** pour la prospection. Utiliser `resend_sender`.
4. **Ne jamais ajouter de génération LLM** dans `copywriter/main.py`. La détection de situation est purement algorithmique.
5. **Ne jamais modifier les templates HTML** (`template_profil_*.html`) sans instruction explicite de l'utilisateur.
6. **Ne jamais approuver des leads automatiquement** sans validation Telegram (`approuve` doit rester à 0 jusqu'à confirmation).
7. **Avant tout changement** dans le pipeline email, relire ce fichier + `envoi/email_builder.py` + `dashboard/pipeline.py`.

### Telegram — Validation des relances

- Les relances suivent exactement le même schéma que l'email initial : ✅/❌ via Telegram
- La génération et la demande d'approval sont dans `sequence_worker.py`
- L'envoi effectif après approbation est dans `email_sequence_service.approve_and_send()`
- Le poller `relance_approval_poll` tourne toutes les 2 minutes
- **Ne pas modifier le callback_id** (`relance_approve_{sequence_id}`) ou la logique pending.db

---

## 7. Scheduler (horaires actifs)

- **10h** : génération emails (post-audit de la nuit)
- **14h** : envoi batch des emails approuvés
- **00h** : scraping nocturne (campagnes planifiées)
- **10h30** + **toutes les heures** : génération des relances planifiées (`sequence_worker`)
- **Toutes les 2 min** : vérification approbations Telegram (relances + step 2)
- **Toutes les 15 min** : détection réponses email (IMAP poll) + maintenance batches
- **Quota** : 60 emails/jour max (`planning_settings.daily_quota`)
- **Backlog** : si ≥ 3 jours de leads → pause de planification

---

## 8. Cycle de relances — flux complet

```
initial email envoyé
  → plan_sequences_for_lead() planifie 3 relances dans email_sequences (statut='planned')
    → sequence_worker (10h30 + toutes les heures) :
        1. Vérifie conditions (pas de réponse, pas de clic)
        2. Met à jour le score du lead
        3. Génère l'email via build_premium_email()
        4. Stocke email_objet + email_corps dans email_sequences
        5. Passe statut='pending_approval'
        6. Envoie notification Telegram avec ✅/❌
    → relance_approval_poll (toutes les 2 min) :
        1. Vérifie pending.db pour les callback_id 'relance_approve_*'
        2. Si status='ok' → approve_and_send() → envoie via Resend
        3. Si envoi OK → marque statut='sent'
```

### Planning des relances

| Type | Délai | Condition |
|------|-------|-----------|
| relance_1 | J+3 | Pas cliqué |
| relance_2 | J+7 | Pas cliqué + email ouvert |
| relance_special | J+14 | Lead chaud/tiède uniquement |

### NE JAMAIS

- Envoyer une relance sans approbation Telegram (statut `pending_approval` obligatoire)
- Court-circuiter `approve_and_send()` — c'est le seul chemin d'envoi validé
- Modifier les colonnes `email_objet` / `email_corps` / `telegram_msg_id` de `email_sequences`

---

## 9. Nettoyage des emails — règles

### `email_valide` (leads_audites)

- `email_valide` ne doit JAMAIS contenir de valeur non-email (`smtp_guess`, `site:home`, `site:/mentions-legales/`, etc.)
- Si l'email n'a pas pu être validé, laisser `email_valide` à NULL
- Le vrai email est toujours dans `leads_bruts.email` (fallback UI)
- **UI**: dans `unified_leads.js`, `sniper.js`, `dashboard_core.js`, `email_valide` n'est affiché que si c'est un vrai email (regex `/^[^\s@]+@[^\s@]+\.[^\s@]+$/`)

### Emails d'agence / placeholders

- `contact@oswald-orb.fr`, `developer@udevweb.co`, `agence@virtuosa.fr`, `contact@joinoko.com` → emails d'agence web, pas les vrais emails des commerces
- `privacy@waze.com`, `support@waze.com` → emails Waze, pas ceux du commerce
- `xxxxxxxx@xxx.com`, `utilisateur@domaine.com` → placeholders
- Ces emails doivent être remplacés par un vrai email (trouvé dans `ml_extracted`, `email_2`, ou rescrape du site)
- Si aucun vrai email trouvé → clear à NULL (pas d'email > mauvais email)

---

## 10. GitHub Pages (audit.incidenx.com)

- Rapports publiés via `synthetiseur/github_publisher.py` → `_commit_files()`
- URL publique : `https://audit.incidenx.com/{slug}/`
- `lien_rapport` en DB stocké comme `local://{slug}/` → remplacé par URL publique avant envoi
- Page de revue Telegram : `https://audit.incidenx.com/reviews/YYYY-MM-DD/`

---

## 11. ⚠️ DÉMARRAGE OBLIGATOIRE POUR TOUT AGENT IA

> **Lue en PREMIER par tout agent (Claude, opencode, Antigravity, etc.) avant de travailler sur ce dépôt.**

**AVANT d'écrire du code, de modifier un fichier ou de répondre à une demande**, tout agent DOIT :

1. **Lire `README.md`** (racine) — il contient le préambule d'onboarding et le point d'entrée.
2. **Charger les skills du projet** dans `.claude/skills/` **dans l'ordre** ci-dessous, selon la tâche.

### Compétences du dépôt (`.claude/skills/`) — ordre de chargement

| Ordre | Skill | Quand le charger | Fichier |
|---|---|---|---|
| 1 | `ia-prospection` (orchestrateur) | Toute demande de prospection IA : « qualifie/traite liste N », « génère les mails », « fais la maquette », « rédige un email ». Délègue aux skills spécialisés ci-dessous. | `.claude/skills/ia-prospection/SKILL.md` |
| 2 | `qualify-leads` | Qualification/scoring d'un lead ou liste : état du site (absent/cassé/daté/moderne), score d'obsolescence 0-100, colonnes `Opportunite/Score/Signaux`. | `.claude/skills/qualify-leads/SKILL.md` |
| 3 | `refonte-extraction` | Maquette (objectif web) : extraire les vraies couleurs/images/textes du client (site réel OU vérité Google Business/Instagram/WebArchive pour lead sans site). Étape 1 de la chaîne refonte. | `.claude/skills/refonte-extraction/SKILL.md` |
| 4 | `refonte-design` | Maquette : direction design verrouillée sur la vérité extraite → DESIGN.md + preview. Étape 2 de la chaîne refonte. | `.claude/skills/refonte-design/SKILL.md` |
| 5 | `refonte-build` | Maquette : coder la page finale vendeuse → `PROMPT/<IdLead>/index.html` + `capture.png`. Étape 3 de la chaîne refonte. | `.claude/skills/refonte-build/SKILL.md` |
| 6 | `audit-web` | Modifier/déboguer tout fichier de `auditeur/` (scoring, PageSpeed, BeautifulSoup) | `.claude/skills/audit-web/SKILL.md` |
| 7 | `error-handler` | Écrire tout `try/except`, gérer des erreurs API, logique de retry | `.claude/skills/error-handler/SKILL.md` |
| 8 | `groq-copywriter` | Modifier `business_copywriter.py` / `handle_llm_call` / `SYSTEM_PROMPT` / `FEW_SHOT` | `.claude/skills/groq-copywriter/SKILL.md` |
| 9 | `google-sheets-agent` | Toute lecture/écriture Google Sheets (`leads_bruts`, `leads_audites`, `emails_envoyes`, `config_comptes`) | `.claude/skills/google-sheets-agent/SKILL.md` |

### Règles de chargement

- **Le skill `ia-prospection` est PRÉPONDÉRANT** pour le faisceau IA (qualification, mails, maquettes).
  Il **suspend explicitement** la section 2 de ce fichier (email_builder seul) pour ce faisceau — décision
  utilisateur assumée. Ne pas le confondre avec les règles 2–8, qui restent inchangées.
- **L'orchestrateur délègue aux skills spécialisés selon la phase**: qualification → `qualify-leads` (2) ;
  maquette web → `refonte-extraction` (3) → `refonte-design` (4) → `refonte-build` (5). Ne pas les
  confondre : `audit-web` (6) concerne l'outil `auditeur/`, pas la maquette des leads.
- Si la tâche touche PLUSIEURS domaines, charge **tous** les skills concernés (ex : qualification + maquette → 1 + 2 + 3 + 4 + 5).
- Si aucun skill ne correspond, travailler directement — mais lire quand même `README.md` d'abord.
- **Ne jamais deviner** le fonctionnement : lire le skill, puis le backend concerné, avant d'agir.

### Synchronisation

- Le contrat canonique vit dans `ia_echanges/PROMPT-SYSTÈME.md` (= version de référence du skill
  `ia-prospection`). Tout agent qui modifie l'un doit maintenir l'autre synchronisé.
