# RUNBOOK — prospection-machine (v2 campagne → liste → prospect)

Guide opérationnel. Les règles normatives vivent dans `AGENTS.md` — ici c'est le
« comment faire » (commandes, sauvegardes, incidentes, tests).

---

## 1. Environnements

| Élément | Valeur |
|---|---|
| Python | `C:\Python314\python.exe` (système) — `.venv\Scripts\python.exe` est CASSÉ, ne pas utiliser |
| Base de données | `data/prospection.db` (SQLite, tables v2 ajoutées par `migrate_v2_schema()`) |
| Node.js (checks syntaxe JS) | `node --check <fichier>.js` |
| Dashboard | `dashboard/app.py` (Flask) |
| UI v2 (V6) | `/` → `views/dashboard_v6.html` + `js/modules/v6_shell.js` (shell v2-only) |
| UI v5 (archive) | `/legacy` → `views/dashboard_v5.html` + `js/modules/dashboard_core.js` (maintenance seulement) |

### UI V6 vs V5 (2026-09-13)

- **V6 (`/`)** : coquille v2-only. Pas de `dashboard_core.js` ; la navigation (`nav`,
  `switchSectionTab`, init des onglets) est fournie par `v6_shell.js` (`window.V6_MODE = true`).
  Sections : Cockpit, **Listes**, Campagne (Leads + Sources), Planificateur, Console Tâches,
  Paramètres (Général + Health + Logs). Exclus (legacy, V5 uniquement) : `collecte.js`,
  `audits.js`, `rapports.js`, `leads.js`, `templates.js`, `relances.js`, `jobs.js`.
- **V5 (`/legacy`)** : archive vivante, NE PAS SUPPRIMER tant qu'elle consomme les modules
  legacy (`email_builder`, `templates/emails`, `routes/emails.py`, `routes/sniper.py`,
  `agents/`, `workers/`, `services/email_generator.py`). Ses onglets legacy sans équivalent v2
  (Suivi CRM/ROI/funnel/export, templates, listes) restent visibles mais pointent sur des
  tables purgées → vides (accepté).

## 2. Tests

```powershell
# Suite v2 — 81 tests (DB temporaire, AUCUN réseau ni hub Telegram réel)
C:\Python314\python.exe -m pytest tests/test_v2_campagnes.py tests/test_v2_listes.py tests/test_v2_replies.py tests/test_v2_envoi.py tests/test_v2_templates.py tests/test_v2_validation.py tests/test_v2_orchestration.py tests/test_v2_relances.py -q

# Toute la suite
C:\Python314\python.exe -m pytest tests/ -q
```

Les tests ne touchent JAMAIS `data/prospection.db` : le fixture `tmp_db` monkeypatche
`database.connection.DB_PATH`. Le hub Telegram (`hub_telegram/pending.db`) n'est jamais
écrit par les tests de validation (fixtures faux `fake_tg` / `fake_gateway`).

**Résultat attendu (2026-09-13)** : suite v2 = `81 passed`. Globalement, la suite passe avec
2 fragilités préexistantes (non liées aux changements UI/backend) :
- `test_browser_manager.py::test_acquire_release` (flaky : passe isolé, sémaphore)
- `test_integration_ia.py::test_integration_scrape_campaign_export_scan` (dépend de l'ordre/exécutions)

Aucun test ne dépend du routage `/` (ni `dashboard_v5`/`dashboard_v6`) : la bascule V6 ne
casse pas la suite.

## 3. Sauvegarde / purge du legacy

> Backup WAL-safe + purge des 13 tables legacy. PAS de rollback après la purge.

```powershell
# Aperçu (dry run ?) : le script fait un backup, contrôle les tables v2 puis purge
C:\Python314\python.exe scripts/purge_legacy.py            # backup + purge réels (--yes pour aller au bout)
```

L'état attendu après purge : `async_tasks, campagnes, ia_executions, listes, mailboxes,
planning_settings, prospect_events, prospects, sequence_templates, sqlite_sequence,
suppression_list, sync_log, system_logs` (leads_bruts, leads_audites, emails_envoyes,
email_events, … supprimées).

## 4. Scraping → une campagne (via sa liste)

```powershell
# CLI directe : la campagne est créée si elle n'existe pas (liste par défaut auto)
C:\Python314\python.exe scraper/main.py --keyword "boulangerie" --city "Cotonou" --objectif "Refonte site web"

# Depuis le dashboard : sélecteur « Campagne » dans Sources → Google Maps > Lancer
# POST /api/scraper/launch  body : { ..., "v2_objectif": "Refonte site web" }
```

Résumé en fin de scraping : `[V2] Importés : N (doublons: x, désinscrits: y)`.

## 5. Flux campagne/liste — allers-retours UI

| Action | Endpoint / Fichier |
|---|---|
| Créer une campagne | `POST /api/v2/campagnes` (`nom`, `description`, `secteur`…) |
| Lister les campagnes | `GET /api/v2/campagnes` (alias : `GET /api/v2/objectifs` → 301) |
| Import CSV/JSON | `POST /api/v2/campagnes/<id>/leads/import` (content_type `text/csv` ou JSON `{"rows": [...]}`) |
| Listing des leads | `GET /api/v2/campagnes/<id>/leads?statut=&q=&limit=` |
| Vue unique lead | `GET /api/v2/leads/<id>` |
| Changement de statut | `PUT /api/v2/leads/<id>/statut` `{"statut": "en_sequence"}` |
| Désinscription | `POST /api/v2/leads/<id>/desinscrire` `{"ne_plus_contacter": true}` |
| **Listes** | `GET/POST /api/v2/listes` ; `PUT/DELETE /api/v2/listes/<id>` ; `POST /api/v2/listes/<id>/archive` (CRUD affiché dans l'onglet Listes V6) |
| Prospects d'une liste | `GET/POST /api/v2/listes/<id>/leads` + `POST /api/v2/listes/<id>/leads/import` |
| Sélecteur côté UI | `dashboard/static/js/modules/campagnes.js` (`localStorage.pm_campagne_id`, repli `pm_objectif_id`) ; `objectifs.js` = shim |
| Kill-switch global auto-send | `GET/PUT /api/v2/auto-send` (case « Auto » topbar) |
| Envoi manuel (cette campagne) | `POST /api/v2/campagnes/<id>/send` (bouton « ▶ Envoyer » : initial + relances dues) |
| Relance directe | `from envoi import sequence_engine; sequence_engine.send_relance(<cid>, <pid>)` |
| Relances dues | `from core.orchestration import relances_due; relances_due(<cid>)` |
| Modèles relance | `envoi.template_registry.add_or_update(campagne_id=..., position=1, delai_jours=3, objet=..., corps=...)` |
| Liste séquence campagne | `GET /api/v2/campagnes/<id>/sequence` (bouton « Séquence » si campagne sélectionnée) |
| Ajouter une étape | `POST /api/v2/campagnes/<id>/sequence` `{"position": 1, "delai_jours": 3, "objet": ..., "corps": ...}` |
| Modifier/supprimer | `PUT /api/v2/sequence-templates/<template_id>` / `DELETE` (modal Séquence : 💾 / 🗑) |
| Actualité réponses (IMAP) | `envoi.reply_poller.run_poll()` — job `v2_reply_poll` (15 min) ; manuel : `POST /api/v2/replies/poll` |
| Dernières réponses/NDR | `GET /api/v2/replies/recent?limit=25` |
| Transitions autorisées | `GET /api/v2/statuts/transitions` (file humaine) |

## 6. Incidents courants

**`sqlite3.OperationalError: no such table: campagnes`**
→ `migrate_v2_schema()` pas exécutée : relancer `init_db()` / `migrate_db()` (idempotent).

**Le scraping ne range pas dans la campagne**
→ Vérifier que `--objectif` est passé (CLI, résolu comme une campagne) ou `v2_objectif` dans le
body JSON (dashboard). Les compteurs `[V2]` en fin de run indiquent si l'insertion a eu lieu.

**Email « désinscrit » réimporté malgré tout**
→ `data_extra` / table vide ? Contrôler `suppression_list` via
`SELECT * FROM suppression_list;` puis `import_lead_as_prospect` (mailto restreint dans
`core/objectif_registry.py`).

**Régression Python (erreurs import)**
→ Toujours tester avec `C:\Python314\python.exe`, jamais `.venv`.

## 7. Prochaines étapes (spéc SaaS)

1. ~~Backend d'envoi unique `envoyer(message, boîte)`~~ → fait (gateway, 7 tests).
2. ~~Registre de templates + variables + passe IA~~ → fait (template_registry + humanize, 11 tests).
3. ~~Validation Telegram par campagne~~ → fait (`validation_telegram`, poller `v2_approval_poll` 1 min, 7 tests).
4. ~~Envoi automatique piloté~~ → fait (kill-switch global + `envoi_auto` par campagne + bouton manuel, orchestration 9 tests).
5. ~~Relances v2~~ → fait (positions > 0, `delai_jours`, max_touches → `sans_reponse`, 6 tests).
6. ~~UI de gestion des relances~~ → fait (modal « Séquence » : positions 0..3, délais, objet/corps, actif, générique vs dédié ; API v2 `sequence` + CRUD templates ; +2 tests).
7. Décommissionnement legacy — purge DB exécutée ✓ ; **code : `sniper/imap_poller.py` supprimé
   (2026-09-13, remplacé par `reply_poller`), jobs scheduler legacy retirés** (`fill_check`,
   `sequence_relances`, `sniper_imap_poll`, `telegram_step2_poll`, `relance_approval_poll`,
   `sniper_generate`, `sniper_send`, registrations registry « Batch Maintenance / Telegram
   Notifications / Auto Approval / Sequence Relances »), `/api/sniper/poll-imap` repointé sur
   `envoi.reply_poller.run_poll`. Backup code : `backups/code_backup_20260913_decommission`.
   Reste à trancher (UI v5) : `email_builder`, `templates/emails`, `routes/emails.py`,
   `routes/sniper.py`, `agents/`, `workers/`, `services/email_generator.py` — toujours référencés
   par des onglets legacy encore affichés.
   **Brique UI (2026-09-13)** : nouvelle coquille **V6 v2-only servie sur `/`**
   (`views/dashboard_v6.html`, `components/sidebar_v6.html`, `components/header_v6.html`,
   `js/modules/v6_shell.js`) ; l'ancienne interface V5 reste **servie sur `/legacy`**
   (archive vivante). `/` ne charge plus `dashboard_core.js` ni les modules legacy.
8. ~~Réponses entrantes (IMAP)~~ → fait (`reply_poller` : ndr/auto_reply/reponse → `a_traiter_humain`, matching par message_id puis From, job 15 min, 12 tests).
9. ~~File humaine~~ → fait (filtre « À traiter (répondu) » + sélecteur rapide « → Statut » par ligne : rdv_obtenu / pas_interesse / a_relancer_plus_tard / ré-ouverture en_sequence ; transitions exposées par `GET /api/v2/statuts/transitions`).
10. ~~Panneau détail prospect~~ → fait (modal 👁 : snippet dernière réponse + timeline d'événements + actions ✅ RDV / ✖ pas intéressé / ⏳ à relancer / 🚫 ne plus contacter).
11. ~~Notification Telegram à la réception~~ → fait (`envoi.telegram_validation.notify_answer` appelée par `reply_poller` sur toute réponse réelle ; jamais bloquant, hermétique en test).
12. ~~UI V6 v2-only sur `/`~~ → fait (routage `dashboard/routes/pages.py` : `/` → `dashboard_v6.html`, `/legacy` → `dashboard_v5.html` ; shell = `v6_shell.js` ; rendu validé + suite complète sans régression). Reste : validation visuelle navigateur, puis masquer/purger les onglets legacy de V5.

## 8. Tunnel d'envoi v2 — commandes utiles

```powershell
# Envoi initial automatisé (élection scheduler) via script :
C:\Python314\python.exe -c "
from envoi import sequence_engine
print(sequence_engine.send_initial(<campagne_id>, <prospect_id>))
"