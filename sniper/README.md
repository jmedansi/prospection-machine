# sniper/ — Pipeline Sniper (High-Ticket B2B)

**Lire ce fichier avant toute modification dans ce dossier.**

---

## Pourquoi ce dossier est séparé

L'ancien pipeline (`scraper/`, `auditeur/`, `copywriter/`, `envoi/`) fonctionne.
Le Sniper a une logique métier différente et ne doit pas le polluer.

**Règle** : aucun fichier de `sniper/` ne doit importer depuis `copywriter/` ou `auditeur/`.
La connexion à l'existant se fait uniquement via la DB et l'`expediteur_agent`.

---

## Ce que fait le Sniper

Trouver des entreprises B2B avec un budget prouvé (elles paient déjà des pubs ou ont un CMS coûteux)
et leur envoyer un email personnalisé avec l'angle exact de leur problème technique.

Différence fondamentale avec le pipeline Maps :
| Pipeline Maps               | Pipeline Sniper                            |
|-----------------------------|--------------------------------------------|
| PME locales (GMB, Maps)     | Annonceurs B2B (Google Ads, tech stack)    |
| Angle : visibilité locale   | Angle : ROI publicitaire / sécurité infra  |
| Source : Google Maps        | Source : Google Ads, annuaires, offres RH  |

---

## Sources (4 construites, testées)

| # | Nom    | Logique                                                       | Statut       |
|---|--------|---------------------------------------------------------------|--------------|
| 1 | Ads    | Mots-clés → Google/Bing Ads (Patchright) → domaines annonceurs | ✅ Fonctionnel |
| 2 | Tech   | API Entreprises (NAF + effectif) + Wappalyzer (blacklist CMS auto-gérés) | ✅ Fonctionnel |
| 3 | Jobs   | Offres d'emploi France Travail (API OAuth2) = signal de budget | ✅ Construit — ⚠️ activer app sur francetravail.io |
| 4 | BODACC | Nominations CEO (familleavis_lib=Créations) + résolution SIREN → NAF filter | ✅ Testé réel |

---

## Flux de données

```
[Source N]
    → scraper/sniper/           ← extraction des domaines
    → scraper/sniper/pipeline.py (Phase 2) ← PageSpeed + Wappalyzer
    → scraper/sniper/scoring.py (Phase 3)  ← tag_urgence + niveau
    → leads_bruts (source='ads'|'tech'|'jobs', donnees_audit=JSON)
         ↓
    sniper/email_generator.py   ← génère email selon tag_urgence
         ↓
    leads_audites (email_objet, email_corps, approuve=0)
         ↓
    [Validation manuelle]
         ↓
    agents/expediteur           ← envoi Resend (PARTAGÉ avec l'ancien pipeline)
```

---

## Tags d'urgence → angles email

| tag_urgence     | Angle                                    | Template                       |
|-----------------|------------------------------------------|--------------------------------|
| `perf`          | ROAS négatif — site trop lent pour les pubs | `templates/email_perf.html` |
| `securite`      | CMS exposé sans CDN/WAF                  | `templates/email_securite.html`|
| `perf+securite` | Double impact — perf + infrastructure    | `templates/email_perf_securite.html` |

---

## Structure du dossier

```
sniper/
├── README.md                    ← ce fichier (LIRE EN PREMIER)
├── __init__.py
├── bodacc_scanner.py            ← Source 4 : scan BODACC quotidien
├── copywriter.py                ← logique email : sélection angle + personnalisation
├── email_generator.py           ← génère + stocke dans leads_audites
├── imap_poller.py               ← détection réponses step 1 (IMAP, */15min)
├── linkedin_agent.py            ← outreach LinkedIn catch-all (Patchright)
├── rapport_generator.py         ← génère rapport HTML + publie Vercel
├── enrichment/
│   ├── pre_filter.py            ← TTFB + GTM + heat score (rejet 80%)
│   ├── contact_finder.py        ← email contact@ + tél depuis le site
│   ├── ceo_finder.py            ← API gouv.fr → Groq → Ollama
│   ├── email_permutations.py    ← 6 variantes prenom.nom@
│   └── smtp_validator.py        ← MX + catch-all + RCPT TO
└── templates/
    ├── email_perf.html
    ├── email_securite.html
    ├── email_perf_securite.html
    └── email_step2_livraison.html

scraper/sniper/                  ← couche acquisition (séparée intentionnellement)
├── ads_extractor.py             ← Phase 1 : keywords → domaines Google/Bing
├── tech_scraper.py              ← Source 2 : API Entreprises + Wappalyzer
├── jobs_scraper.py              ← Source 3 : France Travail OAuth2
├── pipeline.py                  ← orchestrateur complet Phases 1→4
├── scoring.py                   ← tag_urgence + niveau_urgence
├── wappalyzer_runner.py         ← Node.js Wappalyzer via subprocess
└── wappalyzer_check.js
```

---

## Connexion à l'ancien système

**Ce que ce module utilise de l'existant :**
- `database.connection.get_conn()` — accès SQLite
- `database.audits.insert_audit()` — pour créer la ligne `leads_audites`
- `services/sniper_sender_service.py` — envoi Resend step 1 avec quota

**Ce que ce module ne touche PAS :**
- `copywriter/main.py` — logique GMB/Maps, ne pas modifier
- `envoi/email_builder.py` — templates A/B/C/D, ne pas modifier
- `agents/redacteur` — génération email Maps, ne pas modifier

**Routing déjà en place** dans `services/email_generator.py` :
```python
_SNIPER_SOURCES = {"ads", "tech", "jobs", "bodacc"}

def generate_email_for_lead(lead_id):
    src = conn.execute("SELECT source FROM leads_bruts WHERE id=?", (lead_id,)).fetchone()
    if src and src["source"] in _SNIPER_SOURCES:
        from sniper.email_generator import generate_sniper_email_for_lead
        return generate_sniper_email_for_lead(lead_id)
    # sinon logique Maps
```

## Scheduler quotidien

```
07:00  bodacc_daily_scan    → sniper/bodacc_scanner.scan_daily()
08:00  sniper_generate      → services/email_generator (si sniper_auto_generate=1)
08:30  sniper_send          → services/sniper_sender_service.send_sniper_step1()
*/15m  sniper_imap_poll     → sniper/imap_poller.poll_inbox()
```

## Points d'attention

- **BODACC** : SIRENE remplit rarement `site_internet` → les leads sont insérés sans site, le CEO finder enrichit au moment de `sniper_generate`
- **France Travail** : activer l'app `PAR_offresdemploiv2_...` sur francetravail.io (portail partenaire) — actuellement `invalid_client`
- **Quota** : `sniper_daily_quota=20` dans `planning_settings`, modifiable depuis le dashboard (clic sur la carte quota)

---

## Règles pour les agents IA

1. **Lire ce fichier en entier avant toute modification**
2. Ne jamais importer `copywriter.main` depuis ce module
3. Ne jamais créer de nouvelle route Flask ici — passer par `dashboard/routes/campaigns.py`
4. Les templates HTML Sniper sont dans `sniper/templates/` — ne pas les mélanger avec `templates/emails/`
5. `approuve` doit toujours être à `0` à la création — jamais d'auto-approbation
6. Pour ajouter une source : créer `scraper/sniper/source_X.py` + documenter dans ce README
