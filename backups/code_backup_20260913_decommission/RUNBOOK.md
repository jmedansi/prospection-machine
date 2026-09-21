# RUNBOOK — prospection-machine (v2 objectif-driven)

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

## 2. Tests

```powershell
# Suite v2 — 69 tests (DB temporaire, AUCUN réseau ni hub Telegram réel)
C:\Python314\python.exe -m pytest tests/test_v2_objectifs.py tests/test_v2_envoi.py tests/test_v2_templates.py tests/test_v2_validation.py tests/test_v2_orchestration.py tests/test_v2_relances.py tests/test_v2_replies.py -q

# Toute la suite
C:\Python314\python.exe -m pytest tests/ -q
```

Les tests ne touchent JAMAIS `data/prospection.db` : le fixture `tmp_db` monkeypatche
`database.connection.DB_PATH`. Le hub Telegram (`hub_telegram/pending.db`) n'est jamais
écrit par les tests de validation (fixtures faux `fake_tg` / `fake_gateway`).

## 3. Sauvegarde / purge du legacy

> Backup WAL-safe + purge des 13 tables legacy. PAS de rollback après la purge.

```powershell
# Aperçu (dry run ?) : le script fait un backup, contrôle les tables v2 puis purge
C:\Python314\python.exe scripts/purge_legacy.py            # backup + purge réels (--yes pour aller au bout)
```

L'état attendu après purge : `async_tasks, ia_executions, mailboxes, objectifs,
planning_settings, prospect_events, prospects, sequence_templates, sqlite_sequence,
suppression_list, sync_log, system_logs` (leads_bruts, leads_audites, emails_envoyes,
email_events, … supprimées).

## 4. Scraping → un objectif

```powershell
# CLI directe : l'objectif est créé s'il n'existe pas
C:\Python314\python.exe scraper/main.py --keyword "boulangerie" --city "Cotonou" --objectif "Refonte site web"

# Depuis le dashboard : sélecteur « Objectif v2 » dans Sources → Google Maps > Lancer
# POST /api/scraper/launch  body : { ..., "v2_objectif": "Refonte site web" }
```

Résumé en fin de scraping : `[V2] Importés : N (doublons: x, désinscrits: y)`.

## 5. Flux objectif — allers-retours UI

| Action | Endpoint / Fichier |
|---|---|
| Créer un objectif | `POST /api/v2/objectifs` (`nom`, `description`, `secteur`…) |
| Lister les objectifs | `GET /api/v2/objectifs` |
| Import CSV/JSON | `POST /api/v2/objectifs/<id>/leads/import` (content_type `text/csv` ou JSON `{"rows": [...]}`) |
| Listing des leads | `GET /api/v2/objectifs/<id>/leads?statut=&q=&limit=` |
| Vue unique lead | `GET /api/v2/leads/<id>` |
| Changement de statut | `PUT /api/v2/leads/<id>/statut` `{"statut": "en_sequence"}` |
| Désinscription | `POST /api/v2/leads/<id>/desinscrire` `{"ne_plus_contacter": true}` |
| Sélecteur côté UI | `dashboard/static/js/modules/objectifs.js` (`localStorage.pm_objectif_id`) |
| Kill-switch global auto-send | `GET/PUT /api/v2/auto-send` (case « Auto » topbar) |
| Envoi manuel (this objectif) | `POST /api/v2/objectifs/<id>/send` (bouton « ▶ Envoyer » : initial + relances dues) |
| Relance directe | `from envoi import sequence_engine; sequence_engine.send_relance(<oid>, <pid>)` |
| Relances dues | `from core.orchestration import relances_due; relances_due(<oid>)` |
| Modèles relance | `envoi.template_registry.add_or_update(objectif_id=..., position=1, delai_jours=3, objet=..., corps=...)` |
| Liste séquence objectif | `GET /api/v2/objectifs/<id>/sequence` (bouton « Séquence » si objectif sélectionné) |
| Ajouter une étape | `POST /api/v2/objectifs/<id>/sequence` `{"position": 1, "delai_jours": 3, "objet": ..., "corps": ...}` |
| Modifier/supprimer | `PUT /api/v2/sequence-templates/<template_id>` / `DELETE` (modal Séquence : 💾 / 🗑) |
| Actualité réponses (IMAP) | `envoi.reply_poller.run_poll()` — job `v2_reply_poll` (15 min) ; manuel : `POST /api/v2/replies/poll` |
| Dernières réponses/NDR | `GET /api/v2/replies/recent?limit=25` |
| Transitions autorisées | `GET /api/v2/statuts/transitions` (file humaine) |

## 6. Incidents courants

**`sqlite3.OperationalError: no such table: objectifs`**
→ `migrate_v2_schema()` pas exécutée : relancer `init_db()` / `migrate_db()` (idempotent).

**Le scraping ne range pas dans l'objectif**
→ Vérifier que `--objectif` est passé (CLI) ou `v2_objectif` dans le body JSON (dashboard).
Les compteurs `[V2]` en fin de run indiquent si l'insertion a eu lieu.

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
4. ~~Envoi automatique piloté~~ → fait (kill-switch global + `envoi_auto` par objectif + bouton manuel, orchestration 9 tests).
5. ~~Relances v2~~ → fait (positions > 0, `delai_jours`, max_touches → `sans_reponse`, 6 tests).
6. ~~UI de gestion des relances~~ → fait (modal « Séquence » : positions 0..3, délais, objet/corps, actif, générique vs dédié ; API v2 `sequence` + CRUD templates ; +2 tests).
7. Décommissionnement legacy final (purge + suppression `email_builder`/Sniper) — purge scriptée, exécutée.
8. ~~Réponses entrantes (IMAP)~~ → fait (`reply_poller` : ndr/auto_reply/reponse → `a_traiter_humain`, matching par message_id puis From, job 15 min, 11 tests).
9. ~~File humaine~~ → fait (filtre « À traiter (répondu) » + sélecteur rapide « → Statut » par ligne : rdv_obtenu / pas_interesse / a_relancer_plus_tard / ré-ouverture en_sequence ; transitions exposées par `GET /api/v2/statuts/transitions`).

## 8. Tunnel d'envoi v2 — commandes utiles

```powershell
# Envoi initial automatisé (élection scheduler) via script :
C:\Python314\python.exe -c "
from envoi import sequence_engine
print(sequence_engine.send_initial(<objectif_id>, <prospect_id>))
"