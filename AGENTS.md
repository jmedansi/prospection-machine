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

## 1bis. Le v2 — modèle piloté par campagne (Campagne → Liste → Prospect)

> **Ce modèle EST la cible. Le pipeline 1 (legacy) est en décommissionnement** :
> ne pas étendre `leads_bruts` / `leads_audites` / `email_builder` — maintenance uniquement.
>
> Historique 2026-09-13 : la notion d'« objectif » (entité v2) a été remplacée par
> **Campagne → Liste → Prospect**. Les anciens endpoints `/api/v2/objectifs*` sont des
> **alias 301** (`dashboard/routes/objectifs.py`) vers `/api/v2/campagnes*` ; `objectifs.js`
> est un **shim** vers `campagnes.js`. Le terme *objectif* `('web'|'general')` qui subsiste
> dans leads/IA est l'**ancienne classification IA** (lead.objectif), pas le modèle v2.

### Règle dorée
**Un prospect n'existe pas sans campagne (ni sans liste).** L'utilisateur crée sa campagne
(texte libre : « Refonte site web », « Lancement application »…) qui porte la configuration
du cycle de vie, PUIS sa liste (l'unité opérationnelle : 1 scraping / 1 import / 1 secteur).
Tout ingest (scraping Maps, CSV, JSON, IA) doit savoir dans QUELLE campagne ranger les leads
(le `get_or_create_liste()` garantit la liste par défaut de la campagne).

### Schéma v2 (même base `data/prospection.db`, `migrate_v2_schema()` idempotente)
- `campagnes` (ex-`objectifs`) : `id`, `nom` (unique, libre), `objectif_principale`,
  `description`, `secteur`, `validation_telegram` (0=auto, 1=requis), `envoi_auto`
  (1=auto-send, 0=manuel), `max_touches`, `statut` (`actif` / `archive`).
- `listes` : `id`, `campagne_id` (FK), `nom`, `description`, `secteur`, `source`, `statut`
  (`actif` / `archive`). Unité opérationnelle qui PORTE les prospects.
- `prospects` : rattaché à `liste_id`, `statut` = machine à états, `statut_meta` (JSON),
  `data_extra` (JSON libre : lien_maps, logo_url, email_2, campaign_id…).
- `prospect_events` : journal d'audit (`creation`, `status_change`, `desinscription`…).
- `suppression_list` : liste NOIRE GLOBALE — un email désinscrit est rejeté dans TOUTE campagne.

### Point d'entrée unique de l'ingestion — `core/objectif_registry.py` (nom historique conservé)
- `resolve_or_create_objectif(nom_ou_id)` → résout la **campagne** par id (numérique) ou par
  nom, crée à la volée, ignore les campagnes archivées. Retourne `(id, nom)` ou `None`.
- `get_or_create_liste(campagne_id)` → liste par défaut de la campagne (créée si absente).
- `import_lead_as_prospect(campagne_id, lead, source='scraping', data_extra_extra=None)` →
  mapping des clés enrichies (nom/email/telephone/site_web/adresse/ville/rating/nb_avis,
  secteur←category ; extra : lien_maps, logo_url, email_2, email_source, statut_email,
  mot_cle, pays, date_scraping) → `prospects_repo.insert_prospect(liste_id, ...)`.
- Le scraping : `scraper/main.py --objectif <nom|id>` → résolution UNE fois (traité comme
  campagne), insertion miroir v2 après chaque `db_insert_lead` legacy. Le dashboard
  (`POST /api/scraper/launch`, body `v2_objectif`) et
  `services/scraper_runner.launch_scraper(v2_objectif=...)` font passer la valeur.

### UI globale — sélecteur de campagne en haut (topbar)
- Le sélecteur vit dans la **topbar** (`components/header_v6.html`, `#obj-select` — id
  conservés par compat), à l'emplacement de l'ancien filtre. Il pilote TOUS les onglets :
  `campagnes.js` (`localStorage.pm_campagne_id`, repli de lecture `pm_objectif_id` legacy →
  `window._ul.v2CampagneId/v2CampagneNom` + alias dépréciés `v2ObjectifId/v2ObjectifNom`
  via `Object.defineProperty`, exposés par `unified_leads.js` `window._ul = _ul`).
- Leads → endpoints v2 (`/api/v2/campagnes/<id>/leads…`) ; « — Aucune campagne — » =
  repli « Archive » legacy.
- **Stats cockpit campagne-aware** : `GET /api/stats?objectif_id=<id>` (alias conservé,
  le JS passe `_ul.v2CampagneId ?? v2ObjectifId`) → `database.stats._stats_v2(conn, id)`
  (prospects machine à états). Sans `objectif_id` : si les tables legacy (§1) existent encore →
  stats legacy ; sinon (après purge) → **vue v2 GLOBALE** (`_stats_v2(conn, None)` = toutes
  prospects de toutes les campagnes). Audits/scores/ROI à 0 tant que le v2 n'enregistre pas
  ces événements.

### UI globale — coquilles V6 (prod) et V5 (archive)
- **V6 = l'interface de prod**, servie sur `/` (`views/dashboard_v6.html`). Shell v2-only :
  `components/sidebar_v6.html`, `components/header_v6.html`, et la navigation est fournie
  par `js/modules/v6_shell.js` (`window.V6_MODE = true`, `window.nav`, `switchSectionTab`,
  boot DOMContentLoaded). **V6 ne charge PAS `dashboard_core.js`** — ne jamais y réintroduire
  de dépendance ; les init d'onglets V6 vivent dans `v6_shell.js` (`v6LoadSection`).
- **V5 = archive vivante**, servie sur `/legacy` (`views/dashboard_v5.html` + `dashboard_core.js`).
  Maintenance seulement. Tant que V5 existe, ne pas supprimer les modules qu'elle consomme
  (`email_builder`, `templates/emails`, `routes/emails.py`, `routes/sniper.py`, `agents/`,
  `workers/`, `services/email_generator.py`).
- Les JS partagés (ex. `campagnes.js`, `listes.js`, `objectifs.js` (shim), `api.js`/`loadStats`,
  `unified_leads.js`) doivent rester **version-agnostiques** : branches via `window.V6_MODE`
  si besoin, jamais de référence dure à `dashboard_core.js` (ou prévoir un fallback défensif).
- Onglet **Listes** de la V6 : interface **sidebar** (ancienne vue restaurée) — `sections/listes_v6.html`
  + `js/modules/listes.js` (`ListesModule`, DOM `#lists-sidebar-items`, `#liste-search`,
  `#liste-filter-statut`, `#liste-lead-search`, `#liste-lead-tbody`). La sidebar affiche les listes
  de la **campagne active** (topbar), ou **toutes groupées par campagne** quand « Aucune campagne ».
  Clic sur une liste → panneau droit : prospects de la liste (`GET /api/v2/listes/<id>/leads`,
  recherche + pagination) avec actions v2 (éditer → `unifiedLeadsOpenEdit`, statut rapide,
  écarter, désinscrire, supprimer) ; `→ Leads` sélectionne la campagne porteuse et navigue.
  **Clic sur un prospect (table Leads ET panneau Listes) → panneau latéral droit
  porté à l'IDENTIQUE du dashboard V5** (`openLeadPanel(id, tab='audit')`) — jamais
  l'édition ni le modal centré. C'est une **copie stricte (verbatim)** des fonctions
  du panneau de `dashboard_core.js` (V5) : `renderAuditPanel` / `renderEmailPanel` /
  `renderSuiviPanel` + tout le stack (`_row`, `_srcBadge`, `_prospBadge`,
  `_contactPill`, `_scoreBar`, `_renderScoreBars`, `_pil`, `_iaActionBtn`,
  `_renderIAPanel`, `_loadLeadMaquette`) ainsi que `openLeadPanel` / `closeSidePanel` /
  `switchPanelTab` / `loadPanelContent` / `_openPanelWithOverlay`. Ce bloc vit dans
  `unified_leads.js` sous garde `if (typeof window.openLeadPanel !== 'function')`
  (V5 archive fournit les siens via son block Annex-B). NE PAS « adapter » le panneau
  (pas de rendu v2 maison : `_ulPanelInfos` etc. ont été SUPPRIMÉS). Seule différence
  au point d'entrée des DONNÉES (v2) : `loadPanelContent` lit `GET /api/v2/leads/<id>`
  (au lieu de `/api/leads/<id>`) et `_ulPanelComposeLead` remonte `data_extra` du
  prospect à la racine (les renderers V5 attendent ces champs en top-level).
  `skeletonPanel` et `escHtml` sont déjà globaux (`js/ui.js`, chargé en V6).
  Markup : `#lead-details-panel.side-panel` dans `{% block modals %}` de
  `dashboard_v6.html` (include `components/modals/side_panel.html` : onglets
  `switchPanelTab('audit'|'email'|'suivi', this)`, fermeture ✕ ou overlay
  `#panel-overlay`) ; CSS `.side-panel` = `css/components/layout.css` +
  `css/saas-redesign.css`. Sélection : `window._selectedLeadId` (ligne `.selected`).
  `unifiedLeadsChangeStatut`/`unifiedLeadsSave`/`unifiedLeadsDelete` (v2) appellent
  `ListesModule.onProspectsChanged()`. `GET /api/v2/listes/<id>/leads` pose
  `statut_display` (`routes/listes.py`, idem `/api/v2/leads`). Le modal centré
  `#modal-ul-detail`/`unifiedLeadsOpenDetail` existe encore mais n'est plus le chemin
  d'ouverture des lignes.
- Onglet **Leads « toutes campagnes » (V6)** : sans campagne choisie, la V6 charge
  `GET /api/v2/leads` (TOUS les prospects, chaque ligne porte `campagne_id`/`campagne_nom`/
  `liste_id`/`liste_nom` ; `list_prospects` accepte désormais zéro filtre = toutes
  campagnes) et les groupe en **sections par campagne**. L'helper `_ulIsV2()` (=`V6_MODE
  || v2CampagneId`) branche les actions (éditer, écarter, désinscrire, statut, import)
  vers les endpoints v2 ; V5 (archive) conserve ses branches legacy.

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
  Sélection de boîte via `get_next_mailbox(campagne_id, backend_pref)` (actif, quota jour,
  pool de campagne, backend smtp/resend/auto, rotation usage ASC). Incrément `usage_jour`
  JAMAIS en dry_run. Table `mailboxes` épuisée non vide → None (pas de seed depuis .env).
  **Reset quotidien** : `reset_daily_quotas()` (usage_jour=0), job scheduler `reset_daily_quotas`
  à 00:05 — sinon le compteur est monotone et bloque la boîte. Si aucune boîte éligible,
  `envoyer` renvoie une erreur **diagnostique** (`_mailbox_block_reason` : table vide,
  désactivée, quota épuisé, pool campagne, backend).
  **Test = sans quota** : `message['no_quota']=True` → envoi RÉEL (dry_run=False) mais
  `usage_jour` n'est pas incrémenté (email de test vers soi-même) ; `ignore_quota=True`
  lève en plus le critère `usage_jour < quota_jour` dans la sélection de boîte (un test
  doit marcher même quand la boîte est à 40/40). Utilisés par
  `POST /api/v2/leads/<pid>/email/test`.
  **Destinataire de test** : `POST /api/v2/leads/<pid>/email/test` sans `to` choisit
  `EMAIL_TEST_TO` (`.env`, ex. `jmedansi@gmail.com`) puis `RESEND_SENDER_EMAIL` puis
  `BREVO_SENDER_EMAIL` — c'est l'adresse perso de test, PAS le prospect.
  **UI quotas** : `dashboard/routes/mailboxes.py` (`GET/PUT /api/mailboxes[/<id>]`,
  `POST /api/mailboxes/<id>/reset`) + onglet « Boîtes » des Paramètres V6
  (`settings.html` `#mailboxes-tbody`, `settings.js` `loadMailboxes/saveMailbox/
  setMailboxActif/resetMailboxUsage`) pour gérer quota_jour / actif / usage.
  **Mise en forme** : `_dispatch` passe le corps texte brut par `envoi/email_shell.py`
  (`build_html_email`) → coquille HTML propre (paragraphes, liens, signature). Un corps
  déjà HTML complet (`<!DOCTYPE`/`<html`) est transmis tel quel. Le container porte
  `white-space: pre-wrap` : retours ligne simples, espaces répétés et indentation du
  template sont PRÉSERVÉS (pas de `<br>`, pas de collapse HTML).
- `template_registry.py` : templates par campagne ou génériques (`sequence_templates`,
  colonnes `campagne_id` NULL (ex-`objectif_id`), `position`, `delai_jours`, `actif`).
  Dédié > générique.
  Variables autorisées : `{{prenom}} {{entreprise}} {{secteur}} {{site_web}} {{offre}}
  {{mot_cle}} {{email}}` ; `render_template` signale les variables inconnues.
  **`{{corps}}` = placeholder** (là où la passe LLM insèrerait sa production) : substitué
  par le corps par défaut (`_DEFAULT_BODY_CONTENT` de `template_registry.py`) quand aucune
  passe n'a fourni de contenu (aperçu / TEST / humanize off) — JAMAIS laissé littéral.
  **Fallback « entité »** : prospect sans prénom → `prenom` est remplacé par `nom` (puis
  `entreprise`), et `entreprise` par `nom` — jamais « Bonjour , » ni « , » en début d'objet.
  Le seed (`schema.py` `INSERT OR IGNORE` pos 0 générique) doit rester SANS `{{corps}}`
  et ses apostrophes sont DOUBLÉES `''` (SQLite n'accepte pas `\'`).
- `humanize.py → humanize_email(objet, corps, prospect, dry_run)` : passe de réécriture IA
  via `config_manager.handle_llm_call` (Groq). Jamais bloquant : sans clé ou en échec,
  retour à l'original. `dry_run=True` → touche jamais le LLM.
- `sequence_engine.py → send_initial(campagne_id, prospect_id, ...)` : verrous (statut,
  écarté, opposition, email) → rendu position 0 → humanisation → envoi → transition
  `en_sequence` + event `initial` (payload, mailbox_id, message_id). Idempotent.
- **Validation Telegram** : `campagnes.validation_telegram` (0=auto, 1=requis).
  − 1 → `send_initial` rend/stocke le contenu, envoie la demande ✅/❌ (pattern
  `hub_telegram/pending.db`, callback `v2_approve_{prospect_id}`) et passe le prospect
  en attente (event `validation_requete`), aucune transition tant que pas approuvé.
  − ✅ → `approve_and_send_initial(prospect_id)` (poller `v2_approval_poll`, 1 min)
  réutilise le contenu STOCKÉ puis envoie réel. ❌ → `validation_refusee`, rien n'est envoyé.
  − 0 → envoi direct.
- **Les relances (positions > 0) et le quota global vivront dans le scheduler** :
  `send_initial` fait UN envoi (ou UNE demande), atomique.

### Orchestration des envois — `core/orchestration.py`
- **RÈGLE PRODUIT (2026-09) : l'envoi INITIAL est MANUEL SANS EXCEPTION.** Aucun job
  d'auto-envoi d'initial n'existe dans le scheduler (`v2_send_initial` a été SUPPRIMÉ) et
  `run_auto_send()` refuse toute exécution avec `manual=False` (`statut='initial_manuel_obligatoire'`).
  Même si le kill-switch global `v2_auto_send` ou `envoi_auto` est à 1, automatisé = interdit
  pour une touche 0. Chemin d'envoi initial UNIQUE : bouton « ▶ Envoyer » d'une campagne
  (`manual=True`) ou bouton panel « Envoyer le mail » sur un prospect `qualifie`.
- Kill-switch global `planning_settings.v2_auto_send` (toggle « Auto » de la topbar →
  `/api/v2/auto-send`) : verrouillé à `'0'` car sans intérêt pour les initials (aucun
  auto-envoi d'initial possible) ; conservé pour compat.
- `campagnes.envoi_auto` (modal « Gérer la campagne ») : ne concerne QUE les relances
  (voir `_run_v2_send_relances`) — ne recrée jamais d'auto-envoi d'initial.
- `run_auto_send(campagne_id=None, limit_per_campagne=10, manual=False)` :
  − `manual=False` → retour immédiat `initial_manuel_obligatoire`, ZÉRO envoi ;
  − `manual=True` (bouton `POST /api/v2/campagnes/<id>/send` « ▶ Envoyer ») : bypass du
    kill-switch ET de `envoi_auto` (action explicite utilisateur).
  (compat : les kwargs `objectif_id` restent acceptés en alias de `campagne_id`.)
- `candidates_for(campagne_id, limit)` : `qualifie` + non écarté + non opposé + email
  présent + absent de `suppression_list`, FIFO (created_at ASC).
- Jobs scheduler v2 :
  − ~~`v2_send_initial`~~ SUPPRIMÉ (initial = manuel sans exception) ;
  − `v2_send_relances` (10 min) : `ensure_batch_requests()` uniquement (✅ Telegram par
    liste) — aucune exécution directe de `run_relances` en auto ;
  − `v2_batch_poll` (1 min) : `consume_approvals()` → envoi des lots ✅ ;
  − `v2_reply_poll` (15 min) : `envoi.reply_poller.run_poll()` (réponses entrantes) ;
  − `v2_approval_poll` (1 min) : `approve_and_send_initial()` sur callback `v2_approve_*`.

### Relances v2 — `sequence_engine.send_relance()` / `core.orchestration.relances_due()`
- Mécanique : statut détermine la position suivante (`en_sequence→1`, `relance_1→2`,
  `relance_2→3`) ; le template position N (`delai_jours`) est dû quand
  `dernière_touche + delai_jours ≤ maintenant` ; chaque relance repasse par le tunnel
  complet (verrous, rendu, humanisation, transition `relance_k → relance_{k+1}`).
- **RÈGLE PRODUIT (structurelle) : TOUTE relance exige une ✅ Telegram, sans exception.**
  Dans `send_relance()`, `needs_tg = approval != 'auto' and not dry_run` — `validation_telegram`
  ne s'applique qu'à l'INITIAL ; aucune config ne permet une relance sans validation.
  Exceptions : `approval='auto'` (lot déjà ✅ en amont par le batch validator) / `dry_run`.
- Auto-envoi des relances (`scheduler._run_v2_send_relances`) : UNIQUEMENT via
  `relance_batch_validator.ensure_batch_requests()` → un ✅ Telegram par liste → `consume_approvals()`
  → `run_relances(cid, liste_id=..., approval='auto')`. Une campagne `envoi_auto=1` avec
  `validation_relances=0` est IGNORÉE (skip + log) — jamais d'auto-envoi direct.
- Bouton panel « Envoyer le mail » (`POST /api/v2/leads/<id>/email/send`) : prospect
  `qualifie` → initial direct (manuel) ; `en_sequence`/`relance_k` → `send_relance(approval='telegram')`
  (demande ✅/❌, aucun envoi direct).
- `max_touches` (campagnes) : touché → transition `sans_reponse` (cycle fermé).
- **Callback Telegram partagé** `v2_approve_{prospect_id}` : `_request_validation()`
  purge le pending.db avant toute nouvelle demande (l'initial consommé ne bloque pas
  la relance suivante) ; l'event `validation_requete` stocke `step`, `from_statut`,
  `to_statut` + contenu → `approve_and_send_initial()` gère toutes les touches.
- L'UI de gestion des relances vit dans la topbar : bouton « Séquence » → modal
  `modal-obj-sequence` (id conservé) listant les étapes (position 0..3, objet, corps,
  delai_jours, actif). Dédié (campagne_id) vs générique (NULL) — un générique sert de
  secours si aucune étape dédiée n'existe à la même position. API :
  `GET/POST /api/v2/campagnes/<id>/sequence` (alias `/api/v2/objectifs/<id>/sequence`),
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
  (derniers événements). L'ancien `sniper/imap_poller.py` a été SUPPRIMÉ
  (décommissionnement 2026-09-13) ; `/api/sniper/poll-imap` pointe maintenant sur
  `envoi.reply_poller.run_poll`.
- File humaine : filtre « À traiter (répondu) » (`ul-filter-statut`) → sélecteur
  rapide « → Statut » par ligne (options = transitions autorisées de la machine à
  états via `GET /api/v2/statuts/transitions`) : `rdv_obtenu` / `pas_interesse` /
  `a_relancer_plus_tard` / ré-ouverture `en_sequence`/`relance_1`. Rien n'est
  auto-classé (état final `rdv_obtenu` = décision humaine).

### Threading des emails (RFC 2822) — `envoi/threading.py`
- Colonnes `prospect_events` (migration `migrate_emails_threading()`, appliquée au
  démarrage de l'app) : `message_id` = Message-ID RFC réel de l'envoi, `in_reply_to`,
  `references_header` (chaîne References héritée, `threading.extend_references`),
  `parent_event_id` (event parent du fil), `thread_id` (auto-racine à la 1re touche),
  `direction` (`out` | `in`). Index `idx_prospect_events_thread`.
- SMTP (`smtp_sender`) : Message-ID généré via `email.utils.make_msgid`. Resend :
  en-tête `Message-ID` transmis à l'API ; `message_id`=RFC généré, `resend_id`=id interne.
- Relances : `_perform_send` calcule in_reply_to / references / parent_event_id /
  thread_id depuis la dernière touche (`prospects.events`) ; objet préfixé `Re: `
  (`threading.ensure_re`, idempotent re/fw/fwd/tr).
- Réponses entrantes : `find_parent_event` (In-Reply-To exact sinon dernier des
  References) rattache l'event entrant (`direction='in'`) au fil.
- Historique : `prospects_repo.get_thread_for_lead(lead_id)` (lead_id=prospect_id v2,
  ordre chronologique, payload parsé) exposé par `GET /api/email/thread/<int:lead_id>`.

### Panneau latéral — onglet Email (v2, `dashboard/routes/campagnes.py`)
- `GET /api/v2/leads/<int:pid>/email` : aperçu « tel que le prospect le verra ».
  `_render_v2_email()` rend TOUJOURS la position 0 (« Envoi initial ») via
  `template_registry.get_step/render_template` puis `email_shell.build_html_email`
  (HTML final). RÈGLE PRODUIT : l'onglet Email montre la 1re email, jamais une relance
  (initial = manuel ; relances = validation Telegram). Repli sur `data_extra`
  (éditeur) sinon `source:'none'`. **Jamais de passe LLM** (humanize off) : préview = template.
- `POST /api/v2/leads/<int:pid>/email/test` : envoi réel VIA `gateway.envoyer` (quota boîte
  consommé) à `to` (défaut RESEND_SENDER_EMAIL), objet préfixé `[TEST]`. Consomme un slot.
- `POST /api/v2/leads/<int:pid>/email/send` : envoi réel de la prochaine touche
  (`send_initial` direct si `qualifie` — initial manuel ; sinon `send_relance` avec
  `approval='telegram'` — validation Telegram obligatoire, `humanize_on=False`).
- UI : `unified_leads.js` `renderEmailTab`/`_ulFetchV2Email` injecte le rendu dans le lead
  (`email_corps`/`email_objet` top-level) pour les renderers V5 ; `v6_restore.js`
  `panelSendEmail` (bouton « Envoyer le mail » v2), `sendTestEmail` (v2), `previewEmail`,
  `openEmailEditor` (pré-remplissage v2).

### Interdictions (absolues)
1. Ne JAMAIS insérer un lead dans `prospects` sans `liste_id` (donc sans campagne) :
   pas de prospect orphelin. Passer par `import_lead_as_prospect()` / `get_or_create_liste()`.
2. Ne JAMAIS court-circuiter `suppression_list` : un email désinscrit est rejeté partout,
   `statut_dedupe='suppression_list'`.
3. Ne JAMAIS appeler `transition_prospect()` hors de `core/state_machine.py`.
4. Ne JAMAIS étendre le flux legacy (section 1) : il disparaîtra après backup + purge.
5. Toujours résoudre la campagne via `resolve_or_create_objectif()` (nom historique conservé ;
   jamais d'`INSERT` direct dans `campagnes` — sauf `migrate_v2_schema()`).

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
