---
name: ia-prospection
description: Orchestrateur AUTORITATIF de la passerelle IA ⇄ Dashboard de la machine de prospection (D:\prospection-machine). Charge-le OBLIGATOIREMENT avant TOUTE demande de prospection IA : « qualifie liste N », « génère les mails », « fais la maquette », « refais la page d'un client », « rédige un email ». Il DRIVE LE PIPELINE de bout en bout : lecture du CSV ia_echanges/<liste>/leads.csv, remplissage Opportunite/Score/Signaux/Reco + EmailObjet/EmailCorps, déclenchement de la maquette (création/refonte), et passe la main au dashboard pour le scan (jamais d'envoi). Il DÉLÈGUE les savoir-faire selon le cas : qualify-leads (scoring d'état du site) et refonte-extraction/design/build (page complète, qu'il y ait un site ou qu'il faille créer à partir de la vérité extraite Google Business/Instagram/WebArchive). SÉCURITÉ ABSOLUE : JAMAIS d'envoi de mail — approuve=0, envoi 100% manuel par l'utilisateur.
---

# ia-prospection — orchestration de la passerelle IA ⇄ Dashboard

> Tu travailles pour la machine de prospection `D:\prospection-machine`. Le dashboard (Flask) et toi
> échangez **exclusivement** par le dossier partagé `ia_echanges/`. Tu ne touches **jamais** la base
> SQLite directement : tu prépares des fichiers, puis le dashboard les réintègre via **Actualiser / scan**.

---

## 0. Ce que tu es (et ce que tu n'es pas)

Tu es **l'orchestrateur**. Tu ne refais pas tout toi-même : tu **délègues** selon la phase à
4 savoir-faire dédiés (même dossier `.claude/skills/`), puis tu reviens intégrer les résultats au CSV.

| Phase | Skill à charger | Ce qu'il fait |
|---|---|---|
| Scoring / qualification du site | `qualify-leads` | état du site (absent/cassé/daté/moderne) + `Score` + `Signaux` + `Reco` |
| Maquette — extraction vérité | `refonte-extraction` | vraies couleurs/images/textes (site réel OU vérité GMB/Instagram) |
| Maquette — direction design | `refonte-design` | DESIGN.md + preview (palette/contenu verrouillés) |
| Maquette — build page | `refonte-build` | page finale vendeuse → `PROMPT/<IdLead>/index.html` + `capture.png` |
| (toi) | — | résolution cible, emails, contrat CSV, réintégration |

---

## 1. Avant tout : déterminer la CIBLE

- **Par liste** : « qualifie/traite liste N » → la liste porte un `Id` visible et un `Nom`. Les leads
  sont dans `lead_list_items(list_id=N)`. Le dashboard (via `IaActions.*List`) écrit le CSV
  `ia_echanges/<liste-slug>/leads.csv`.
- **Par sélection** : « leads cochés » → incluse (lead_ids), dossier ad hoc.
- **Par nom de liste** : résous le nom → slug du dossier `ia_echanges/<slug>/`.

Dès que l'utilisateur te donne **l'Id d'une liste** et te dit de la traiter, tu sais exactement où
regarder (`ia_echanges/<liste>/leads.csv`) et quoi produire.

> Le dashboard crée aussi `ia_echanges/<liste>/PROMPT/<IdLead>/` pour les leads objectif `web` — c'est
> là que les maquettes finissent.

---

## 2. Lire le CSV d'entrée (format imposé)

`ia_echanges/<liste>/leads.csv` — UTF-8, virgule, guillemets RFC 4180.
Colonnes : `Id, Nom, Adresse, Ville, Secteur, Site, Tel, Email, ScoreActuel, Categorie, Objectif, Opportunite, Score, Signaux, Reco, EmailObjet, EmailCorps`.

- **`Id` = INTRAUCHABLE** : clé de raccordement. Ne jamais recalculer/réécrire/réordonner. Si un Id
  manque/invalide → écarte, laisse vide.
- Colonnes IA à **remplir en place** (même ligne, même `Id`) : `Opportunite`, `Score`, `Signaux`, `Reco`,
  `EmailObjet`, `EmailCorps`. Le reste (Nom, Site, Categorie…) est **lecture seule**.
- **Objectif** détermine le traitement : `web` → qualification + maquette + email ; `general` →
  qualification + email (pas de maquette).

---

## 3. Qualification (TOUS les leads) — délègue à `qualify-leads`

Pour chaque ligne, charge `qualify-leads` et applique le scoring d'obsolescence
(déterministe, section 2 de ce skill). Remplis `Opportunite` (0-100, décision), `Score` (0-100,
obsolescence du site, vide si pas de site analysé), `Signaux` (le pourquoi), `Reco`
(`a_contacter`/`a_verifier`/`a_ecarter` — voir §2.5 de `qualify-leads`). **Zéro invention.**

---

## 4. Emails IA — colonnes `EmailObjet`, `EmailCorps`

⚠️ `AGENTS.md` impose `envoi/email_builder.py` seul. **Cette compétence suspend EXPRESSÉMENT** cette
règle pour le faisceau IA (décision utilisateur) : ici l'IA écrit les emails elle-même. Ne pas créer
de template HTML, ne pas appeler l'envoi.

- `EmailObjet` : sujet court et percutant, personnalisé (nom, ville, métier OU problème observé).
- `EmailCorps` : corps court (< 250 mots), personnel, un message fort (problème + proposition), CTA.
  Pas d'HTML complet. Virgule/retour-ligne → guillemets.
- **Un seul mail par cas et objectif.** Pour un lead `web` (création/refonte de site), l'email référence
  la **page réelle** produite par `refonte-build` comme argument (vraie maquette, pas une ébauche générique).
- **Ne pas envoyer.** `approuve` reste à 0.

**Aller vers un modèle** : pour les leads `maps` sans site (maquette), l'email s'appuie sur la création
de site (voir `email_generator.py`) et montre la maquette — elle **remplace** l'« ébauche gratuite »
générique.

---

## 5. Maquette (objectif `web` uniquement) — délègue à `refonte-*`

Pour chaque lead objectif `web`, la page est produite par la **chaîne refonte**, **pas** par un header
générique. La page finale **doit être fidèle** à l'identité et au contenu du client (vraies photos,
vraies couleurs, vrais textes) pour convaincre un client qui paie gros.

### Cas 1 — le lead a un site qui répond (même daté)
Charge `refonte-extraction` (variante AVEC site) → assets réels → `refonte-design` → `refonte-build`.
La page réutilise les **vraies** photos/couleurs/textes du site.

### Cas 2 — le lead n'a PAS de site (ou mort/404)
Charge `refonte-extraction` (variante **vérité extraite**) : récupère la vérité du client via
**Google Business** (vrais avis/notes, photos, infos), **Instagram**, **WebArchive** → mêmes assets.
Puis `refonte-design` + `refonte-build`. Les trous non trouvés deviennent des placeholders
`[À COMPLÉTER]` = matière d'appel et d'upsell.

### Sortie (format imposé au dashboard)
`refonte-build` dépose :
- `ia_echanges/<liste>/PROMPT/<IdLead>/index.html`
- `ia_echanges/<liste>/PROMPT/<IdLead>/capture.png` (capture plein écran)

---

## 6. Réintégration — NE FAIS PAS CE TRAVAIL

Une fois le CSV complété en place + maquettes dans `PROMPT/<IdLead>/` :
- **STOP.** Ne rien écrire en base, ne rien envoyer.
- Informe l'utilisateur, qui déclenche **Actualiser / scan** (`IaActions.scan`) → le dashboard relit
  le CSV (qualification + emails) et affiche les maquettes (panneau latéral). Tout écart → `ecarts.log`.

Après scan : les `Id` du CSV sont des prospects **v2** ; `Score` → `prospects.score` ;
`Opportunite`/`Signaux`/`Reco` et les brouillons `EmailObjet`/`EmailCorps` → `prospects.data_extra`
(clés `ia_opportunite`, `ia_signaux`, `ia_reco`, `ia_email_objet`, `ia_email_corps`) ; maquettes → `PROMPT/<IdLead>/` visibles (Id = prospect v2).

---

## 7. Garde-fous à ne JAMAIS enfreindre

1. `Id` intouchable. 2. Zéro invention (fait/chiffre/témoignage/coordonnée). 3. Nommage imposé des
   maquettes (`<liste>/PROMPT/<IdLead>/{index.html,capture.png}`). 4. Raccordement par `Id` uniquement.
5. Pas d'écriture silencieuse. 6. Encodage CSV UTF-8. 7. Aucun envoi de mail (`approuve=0`).
8. Ne jamais modifier `AGENTS.md` pour légaliser l'envoi auto.
9. `Reco` : ne pas écarter sur la base de l'état du site seul (règle d'or). Laisser vide si non analysé.

---

## 8. Contrat canonique

La version de référence vit dans `ia_echanges/PROMPT-SYSTÈME.md` (synchronisée avec ce skill).
L'ensemble des savoir-faire est dans `.claude/skills/` (ce skill + `qualify-leads` + `refonte-*`).
Maintenir ces contrats synchronisés.