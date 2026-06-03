# MASTER PLAN : "SaaS Machine 2026" - Prospection Autonome

Ce document est le cahier des charges absolu et définitif. Il contient des instructions **strictes, concrètes et exécutables** par n'importe quel agent IA. Il couvre la stabilisation immédiate du système, la mise en place d'une architecture résiliente "Zéro Crash", l'automatisation intégrale du pipeline (du scraping aux relances) et une interface utilisateur premium digne de 2026.

**Chemin du fichier :** `d:\prospection-machine\refact\PLAN_SAAS_MACHINE.md`

---

## 🛠️ PHASE 1 : STABILISATION IMMÉDIATE (Le Plan d'Urgence)
*Objectif : Corriger tous les bugs de surface, afficher les bons statuts, nettoyer l'UI et fiabiliser la reprise après crash.*

### 1.1 Correction des Sources de Campagnes
- **Fichier** : `services/scraper_runner.py`
  - **Instruction** : Ligne ~28, remplacer l'appel à `insert_campaign` par `from services.campaign_tracker import create_campaign`. Utiliser `camp_id = create_campaign(campaign_name, keyword, city, source='maps', nb_demande=limit)`.
- **Fichier** : `services/sniper_runner.py`
  - **Instruction** : Vérifier que les fonctions `launch_sniper`, `launch_fb_ads_scraper` et `launch_tech_scraper` forcent respectivement `source='ads'`, `source='fb_ads'`, `source='ecom'`.
- **Fichier** : `database/campaigns.py`
  - **Instruction** : Supprimer l'ancienne fonction `insert_campaign` ou la router vers `campaign_tracker.create_campaign` pour unifier le code.

### 1.2 Boutons d'Action & Statuts (UI Sources)
- **Fichier** : `dashboard/static/js/modules/sources.js`
  - **Instruction** : Dans `renderCampaignsTable()`, lire la variable `c.phase` pour les badges. 
  - Si `c.phase === 'failed'` ou `'stopped'`, afficher les boutons `<button onclick="api_campaign_resume(c.id)">Continuer</button>` et `<button onclick="api_campaign_delete(c.id)">Abandonner</button>`.
  - Afficher `<div class="error-text">${c.error_message}</div>` sous le nom de la campagne en cas d'échec.

### 1.3 Point de Chute et Reprise (Résilience)
- **Fichier** : `services/campaign_tracker.py`
  - **Instruction** : Dans `update_progress`, s'assurer que le paramètre `processed` est sauvegardé. Ce `processed` servira d'`offset`.
- **Fichier** : `scraper/main.py` et `scraper/sniper/pipeline.py`
  - **Instruction** : Ajouter un argument CLI `--offset`. Lors du lancement, ignorer les *N* premiers éléments (ex: index dans la liste des mots-clés ou liste des URLs) pour reprendre exactement là où la campagne a planté.

### 1.4 Nettoyage Leads Station
- **Fichier** : `dashboard/templates/views/sections/leads_unified.html`
  - **Instruction** : Supprimer purement et simplement le bloc `<div class="launch-modals">` (et ses formulaires Maps / FB Ads). L'initiation de campagnes se fait uniquement depuis le Planificateur ou le panneau Sources.
- **Fichier** : `dashboard/static/js/modules/unified_leads.js`
  - **Instruction** : Nettoyer les fonctions associées à l'ouverture de ces anciennes modales.

### 1.5 Relance Manuelle du "Email Finder"
- **Fichier** : `dashboard/routes/leads.py`
  - **Instruction** : Créer la route `POST /api/leads/<int:lead_id>/find-email`. Cette route appelle le script `agents/enrichisseur_agent.py` de manière unitaire.
- **Fichier** : `dashboard/static/js/modules/dashboard_core.js` (Panneau latéral)
  - **Instruction** : Si le lead affiché a un champ `email` vide, injecter un bouton `<button onclick="triggerEmailFind(id)">Chercher Email</button>`. S'il clique, afficher un loader, puis rafraîchir.

### 1.6 Refonte du Planificateur
- **Fichier** : `dashboard/templates/views/sections/planificateur.html`
  - **Instruction** : Remplacer les champs statiques par un `<select id="source-selector">` avec les options (Maps, Ads, FB Ads, E-com). Utiliser du JS pour afficher uniquement les champs requis (ex: masquer "Secteur" si "E-com" est sélectionné).
- **Fichier** : `dashboard/scheduler.py`
  - **Instruction** : Dans `run_planned_scrapings()`, mapper correctement le champ `source` de la base de données vers le bon runner (`launch_scraper` vs `launch_tech_scraper`).

### 1.7 Fiabilisation de la Boucle d'Agents (Audits & Emails Manqués)
- **Fichier** : `dashboard/pipeline/scraper_loop.py` ou équivalent (orchestrateur)
  - **Instruction** : Les audits ont été manqués car l'orchestrateur s'est perdu. Envelopper l'exécution de l'agent `auditeur_agent.py` et `business_copywriter.py` dans un bloc `try/except` isolé pour chaque lead.
  - Si le lead #X plante (ex: timeout site web), le marquer comme `audit_failed` et passer immédiatement au lead #X+1. Vérifier que la séquence `Scrap -> Enrich (Email) -> Audit -> Copywriting` est bien enchaînée et qu'aucun lead n'est ignoré silencieusement.

### ✅ TESTS DE VALIDATION POUR L'AGENT (PHASE 1)
L'agent DOIT exécuter ces commandes pour valider son travail avant de passer à la phase suivante :
1. **Validation Source** : `python -c "from services.campaign_tracker import create_campaign; print(create_campaign('Test', 'IT', 'Paris', 'fb_ads', 10))"` (Vérifier que la DB contient bien `fb_ads`).
2. **Validation Reprise (Offset)** : Lancer le scraper manuellement avec `--offset 2` et `--limit 5`, vérifier dans les logs qu'il n'a traité que 3 éléments au lieu de 5.
3. **Validation Route Email** : `curl -X POST http://localhost:5001/api/leads/XYZ/find-email` (Remplacer XYZ par un ID valide et s'attendre à un statut 200).
4. **Validation Boucle** : Simuler une erreur critique dans `auditeur_agent.py` avec `raise Exception("Test")` et lancer la boucle. Vérifier que l'orchestrateur ne plante pas et que le lead est noté comme échoué, tandis que le reste du script continue.
---

## 🏗️ PHASE 2 : RÉSILIENCE "ZÉRO CRASH" (Architecture Asynchrone)
*Objectif : Le système ne doit plus jamais planter. On abandonne les threads au profit d'un Queueing System professionnel.*

### 2.1 File d'Attente (Message Broker)
- **Outil** : `Redis` + `Celery` (ou `RQ` pour la simplicité en Python).
- **Fichiers** : `services/tasks.py` (Nouveau)
  - **Instruction** : Remplacer TOUS les `threading.Thread(...)` par des tâches Celery : `@celery.task`.
  - Créer des tâches atomiques : `task_scrape(camp_id)`, `task_enrich(lead_id)`, `task_audit(lead_id)`, `task_generate_email(lead_id)`.
  - **Bénéfice** : Si une tâche d'audit échoue (ex: timeout API GPT), Celery gère le retry exponentiel automatiquement. La "machine" ne s'arrête jamais.

### 2.2 Centre Global de Notifications
- **Fichier DB** : `schema.py`
  - **Instruction** : Créer une table `system_logs` (id, type [info, warning, error, fatal], message, source, created_at, is_read).
- **Fichier** : `dashboard/templates/base.html`
  - **Instruction** : Ajouter une icône cloche (Notification Bell) en haut à droite avec un badge dynamique.
- **Fichier API** : `dashboard/routes/health.py`
  - **Instruction** : Capter toutes les exceptions levées par les *Runners* ou *Agents* et faire un `INSERT` dans `system_logs`. 

### 2.3 Le Temps Réel (WebSockets)
- **Outil** : `Flask-SocketIO`
- **Instruction** : Remplacer les appels répétitifs (`setInterval(fetch, 5000)`) dans `scraper_watchdog.js` et `sources.js` par une connexion WebSocket. 
- Lorsque `update_progress()` est appelé côté serveur, émettre un événement `socket.emit('progress', data)`. L'UI est fluide et instantanée, digne d'un SaaS moderne.

### ✅ TESTS DE VALIDATION POUR L'AGENT (PHASE 2)
L'agent DOIT exécuter ces commandes pour valider son travail avant de passer à la phase suivante :
1. **Validation Celery** : Lancer un Worker `celery -A services.tasks worker -l info`. Soumettre une tâche asynchrone `task_audit.delay(lead_id)` via un terminal Python et vérifier l'exécution dans les logs du worker.
2. **Validation Notifications** : `python -c "from database.connection import get_conn; conn=get_conn(); conn.execute('INSERT INTO system_logs (type, message) VALUES (\"error\", \"Test Notification\")'); conn.commit()"` puis vérifier via l'API que le badge s'affiche.
3. **Validation WebSockets** : Écrire un mini-script Python SocketIO Client pour se connecter au port 5001, écouter l'event `progress` et vérifier que la donnée arrive instantanément lorsqu'on lance un scraping.
---

## 🧠 PHASE 3 : PIPELINE INTELLIGENT (La Machine Automatisée)
*Objectif : Le système prend des décisions, qualifie les prospects et adapte son discours, du scraping jusqu'aux relances.*

### 3.1 "Auto-Pilot" (Prospection Continue)
- **Fichier** : `dashboard/scheduler.py`
  - **Instruction** : Créer le job `cruise_control_manager()`. Si le total d'emails envoyés aujourd'hui est inférieur au quota (ex: < 100), piocher de manière autonome un nouveau mot-clé dans une "Banque de mots-clés" (table `keywords_bank`) et lancer une campagne automatiquement.

### 3.2 "Waterfall" Email Finder
- **Fichier** : `agents/enrichisseur_agent.py`
  - **Instruction** : Coder un pattern *Fallback* (Waterfall). 
    1. Appel `Scrap.io` (Recherche principale). Si échoue ->
    2. Appel `CEO Finder / LinkedIn` (Agent IA qui cherche le dirigeant).
    3. *Note : Pas de Hunter.io. Si aucune des deux étapes ne trouve d'email, laisser le champ vide pour un traitement manuel par l'utilisateur.*
  - Enregistrer la source de l'email trouvé en base de données (`email_source`).

### 3.3 Qualification IA (Lead Scoring)
- **Fichier** : `services/lead_scoring_service.py` (Nouveau)
  - **Instruction** : Après l'étape d'audit, envoyer les données JSON de l'audit à un LLM (Claude/Groq) avec le prompt : *"Analyse cet audit et donne une note de 0 à 100 sur la nécessité de nos services."*
  - Sauvegarder cette note dans `leads_audites.score_temperature`.

### 3.4 Priorisation Intelligente (Respect STRICT de AGENTS.md)
- **Fichier** : `dashboard/pipeline.py`
  - **Instruction** : Le système de templates HTML (`template_profil_a.html`, etc.) est régit par une règle absolue détaillée dans `AGENTS.md` (sélection algorithmique via `phrase_synthese`). Il ne faut **surtout pas** créer de nouveaux templates IA.
  - Le `score_temperature` calculé à l'étape 3.3 servira uniquement à **trier** l'ordre d'envoi dans la file d'attente Resend et à mettre en valeur les prospects "Chauds" (Score > 80) dans l'interface Kanban, sans modifier le copywriting strict.

### 3.5 Tracking d'Envoi (Webhooks)
- **Fichier** : `dashboard/routes/webhooks.py` (Nouveau)
  - **Instruction** : Coder le endpoint `POST /api/webhooks/resend`. Configurer Resend pour pinger cette URL.
  - Intercepter les événements `email.opened` et `email.clicked`. Mettre à jour la table `emails_envoyes` avec les timestamps réels.

### 3.6 Relances Dynamiques
- **Fichier** : `workers/sequence_worker.py`
  - **Instruction** : Avant d'envoyer la séquence J+3, vérifier si `emails_envoyes.replied_at` ou `clicked_at` n'est pas nul. Si le prospect a répondu, *annuler* la relance automatiquement pour éviter un double contact gênant.

### ✅ TESTS DE VALIDATION POUR L'AGENT (PHASE 3)
L'agent DOIT exécuter ces commandes pour valider son travail avant de passer à la phase suivante :
1. **Validation Waterfall** : Modifier temporairement `Scrap.io` pour qu'il retourne `None`. Lancer `enrichisseur_agent.py` sur un domaine et vérifier dans la console que le script passe en "fallback" sur le `CEO Finder` avec succès, et s'arrête proprement s'il ne trouve rien.
2. **Validation Scoring** : Lancer `python -c "from services.lead_scoring_service import score_lead; print(score_lead(LEAD_ID))"` et vérifier que la DB enregistre un score entre 0 et 100 dans `leads_audites.score_temperature`.
3. **Validation Webhooks** : Simuler un POST avec la commande `curl -X POST -H "Content-Type: application/json" -d "{\"type\":\"email.opened\",\"data\":{\"email_id\":\"XXX\"}}" http://localhost:5001/api/webhooks/resend`. Vérifier que la table `emails_envoyes` est mise à jour.
---

## 💎 PHASE 4 : UI/UX PREMIUM 2026 (Expérience Utilisateur)
*Objectif : Transformer une simple interface d'administration en un véritable SaaS de pointe (Visuel, Rapidité, Efficacité).*

### 4.1 Vue "Kanban Board"
- **Outil** : `Sortable.js`
- **Fichier** : `dashboard/templates/views/sections/leads_unified.html`
  - **Instruction** : Créer un mode d'affichage "Vue Pipeline" à côté de la "Vue Liste".
  - Colonnes verticales : `Scrapé` | `Audit Prêt` | `Email Généré` | `Envoyé` | `Répondu`.
  - Glisser-déposer (Drag & Drop) qui déclenche une requête `/api/leads/<id>/update-status`.

### 4.2 La "Command Palette" (Raccourci Cmd + K)
- **Outil** : Librairie JS type `ninja-keys`.
- **Fichier** : `dashboard/static/js/core/cmd_k.js` (Nouveau)
  - **Instruction** : Un appui sur `Ctrl+K` ou `Cmd+K` ouvre un modal flouté au centre de l'écran.
  - Taper "Plomberie" cherche instantanément dans les campagnes et les leads. Taper "Auditer..." propose l'action de lancer un audit de masse. Navigation 100% au clavier.

### 4.3 Streaming Visuel IA (Effet "Wow")
- **Fichier** : `dashboard/templates/components/modals/modal_edit_email.html`
  - **Instruction** : Lors de l'édition manuelle ou la regénération d'un email via l'IA, utiliser l'API Fetch avec `response.body.getReader()`.
  - Au lieu d'attendre 5 secondes avec un spinner, afficher les mots générés par l'IA en temps réel sur l'écran (effet machine à écrire).

### 4.4 Dashboard ROI (Chiffre d'Affaires Projeté)
- **Fichier** : `dashboard/templates/views/sections/cockpit.html` (Home)
  - **Instruction** : Remplacer les simples "Nombres d'emails envoyés" par des KPIs financiers.
  - Ajouter un encart "Pipeline Financier Estimé" : `(Nombre de Leads "Répondu") * (Panier moyen défini dans Settings)`.

### 4.5 Dark Mode Natif & Glassmorphism
- **Fichier** : `dashboard/static/css/style.css`
  - **Instruction** : Imposer un Dark Mode profond. Utiliser `background-color: #000000` ou `#0A0A0A`.
  - Pour toutes les modales, cartes et headers, utiliser du Glassmorphism : `background: rgba(255, 255, 255, 0.03); backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.1);`.
  - Mettre en valeur les statuts (OK, Erreur) par des ombres portées au néon (`box-shadow: 0 0 10px var(--color-success)`).

### ✅ TESTS DE VALIDATION POUR L'AGENT (PHASE 4)
L'agent DOIT exécuter ces actions pour valider son travail avant de terminer :
1. **Validation Kanban** : Invoquer l'API JS simulée d'un Drag & Drop d'un élément de "Scrapé" vers "Audité" et vérifier dans la base de données SQLite que le statut du lead a bien été mis à jour.
2. **Validation Cmd+K** : Injecter en console de test navigateur `document.dispatchEvent(new KeyboardEvent('keydown', {'key': 'k', 'metaKey': true}))` et s'assurer (via puppeteer ou un test de retour UI) que la modale `Command Palette` devient visible dans le DOM.
