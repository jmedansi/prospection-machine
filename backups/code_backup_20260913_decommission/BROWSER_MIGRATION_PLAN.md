# Plan de migration : Gestion centralisée async des navigateurs

But & portée
-----------
- But : corriger les fuites / usage excessif de navigateurs et éliminer les erreurs `greenlet.error` en migrant vers une gestion centralisée asynchrone des navigateurs (pool, timeouts, cleanup, monitoring, tests).
- Portée : refactor des agents qui ouvrent/ferment des navigateurs (audits, scrapers, email finder), intégration de `browser_manager.py`, ajout de tests unitaires/integration/charge et procédures CI.

Prérequis
---------
- Python 3.10+ (ou 3.11/3.14).
- `playwright` (ou `patchright`) installé. Exécuter `playwright install` si besoin.
- Chrome disponible pour CDP si partie CDP utilisée (optionnel si headless Playwright suffit).
- Outils tests : `pytest`, `pytest-asyncio`, `psutil`.

Design général
---------------
- Centraliser toutes les opérations Playwright via `BrowserManager` (API async) : pool (Semaphore), `acquire_page()/release_context()`, `page_from_shared()`, `shutdown()`.
- Interdire le mélange sync/async dans un même flow : utiliser API async de bout en bout ou isoler le sync dans un processus séparé.

Tâches détaillées (pour un autre agent)
--------------------------------------
1) Préparations
   - Ajouter variables d'environnement : `BROWSER_POOL_MAX`, `BROWSER_ACQUIRE_TIMEOUT_S`.
   - Mettre à jour `requirements-dev.txt` : `pytest-asyncio`, `psutil`.

2) Consolider `browser_manager.py`
   - Vérifier/compléter `browser_manager.py` : metrics (open_contexts, acquires, releases), logging, watchdog pour contexts ouverts > X sec, config via env.
   - Gérer proprement `TargetClosedError` et `greenlet.error` (log + retry/backoff), sans masquer bugs.

3) Refactorer modules principaux
   - `auditeur/agents/web_analyzer.py`
     - Transformer `measure_local_speed` en `async def` utilisant `async with manager.get_page()` ou `page_from_shared()`.
     - Transformer `run_web_analysis` en async; appeler depuis `auditeur/main.py` via `safe_run_async()`.
   - `scraper/email_finder.py`
     - Remplacer fallback Playwright sync par usage async de `BrowserManager` (fonction async `_scrape_page_with_browser_async`).
     - Garder option feature flag `_PLAYWRIGHT_ENABLED`.
   - `auditeur/main.py`
     - Appels à `run_web_analysis` via `safe_run_async(run_web_analysis(...))`.
     - Documenter et réduire `nest_asyncio` usage.

4) Signal handling & shutdown
   - Ajouter handlers SIGTERM/SIGINT pour appeler `await manager.shutdown()` et garantir cleanup.
   - Préserver `close_all_browsers_sync()` comme emergency fallback.

5) Monitoring & metrics
   - Exposer métriques: `open_contexts`, `semaphore_used`, `acquire_timeouts`, `error_counts`.
   - Option simple : endpoint `/metrics` ou logging périodique.

6) CI / Tests
   - Unit tests (`pytest-asyncio`) pour `BrowserManager` (acquire/release/shutdown/exception release).
   - Integration headless test (staging) : concurrency test, assert `open_contexts <= max_concurrent`.
   - Regression test: lancer N audits concurrents et vérifier absence de `greenlet.error`.
   - Leak detection: run batch of audits; assert aucune instance chrome/playwright zombie (via `psutil`).
   - Load script : `tools/load_test_audits.py` pour mesurer mémoire et erreurs sous charge.

7) Déploiement progressif
   - Déployer en staging, exécuter tests de charge; monitorer logs et métriques.
   - Rollout progressif en production (10% → 50% → 100%).

Modifications fichier-par-fichier (concrètes)
-------------------------------------------
- `browser_manager.py` : metrics, env config, watchdog, logs détaillés, release garanti.
- `auditeur/agents/web_analyzer.py` : rendre async, remplacer cdp usages sync par `BrowserManager`.
- `scraper/email_finder.py` : async browser fallback.
- `auditeur/main.py` : utiliser `safe_run_async` pour appels async internes.
- `core/browser.py` : garder sync API pour compat mais documenter clairement l'usage (ne pas appeler sync depuis async).

Tests de validation (exemples)
------------------------------
- `tests/test_browser_manager.py` (pytest-asyncio)
  - test_acquire_release: acquérir jusqu'au max, vérifier blocage, release, réacquérir.
  - test_exception_releases: provoquer exception puis vérifier sémaphore libéré.
  - test_shutdown_cleans: ouvrir contexts, shutdown(), vérifier fermeture.

- `tests/integration_test_headless.py` (pytest-asyncio, staging)
  - manager max_concurrent=3; lancer 5 tâches naviguant vers example.com; assert succès et `open_contexts <= 3`.

- `tests/regression_no_greenlet.py`
  - exécuter N audits concurrents (simulés) ; assert `errors.log` ne contient pas `greenlet.error`.

- Leak detection & load test (script)
  - `tools/load_test_audits.py --concurrency 20 --runs 100`
  - Vérifier mémoire, process count, error rate.

Critères d'acceptation
----------------------
- Aucune trace `greenlet.error` dans `errors.log` après tests.
- Mémoire stabilisée après montée puis arrêt de charge.
- `open_contexts` max respecte `BROWSER_POOL_MAX`.
- Tous contexts/pages fermés après `manager.shutdown()`.
- Tests unitaires & d'intégration passent.

Commandes utiles
----------------
```bash
# installer dépendances
python -m pip install -r requirements-dev.txt
python -m pip install -r requirements.txt
playwright install

# lancer tests rapides
pytest tests/test_browser_manager.py::test_acquire_release -q
pytest tests/integration_test_headless.py -q

# lancer la batterie complète
pytest -q

# lancer test de charge (staging)
python tools/load_test_audits.py --concurrency 20 --runs 100

# vérifier absence de greenlet.error
grep -n "greenlet.error" errors.log || echo "No greenlet.error found"
```

Pièges & recommandations
-------------------------
- Ne pas patcher simplement la callback de `patchright` ; corriger le mix sync/async.
- Si legacy sync code must remain, isoler dans un sous-processus (not in-thread) to avoid greenlet/thread interactions.
- Utiliser timeouts, retries et backoff, et hooks d'alerte (Telegram/webhook) si erreur répétée.

Livrables attendus
------------------
- Code modifié (`browser_manager.py`, modules refactorés)
- Tests unit/integration/regression
- Script load test
- Rapport de validation (logs + métriques)

---

Fichier créé: `BROWSER_MIGRATION_PLAN.md` à la racine de `prospection-machine`.

Si vous voulez, je peux générer maintenant les skeletons de tests et le script de charge (option A) ou démarrer la PR de refactor (option B).