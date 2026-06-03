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

- **Profil A** : `{NOM} n'a pas de site web — voici ce que ça coûte`
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
