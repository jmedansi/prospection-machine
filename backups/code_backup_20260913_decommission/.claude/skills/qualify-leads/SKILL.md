---
name: qualify-leads
description: Savoir-faire de QUALIFICATION pour la machine de prospection (D:\prospection-machine) quand un lead est déjà en base. Charge-le OBLIGATOIREMENT pour qualifier un lead ou une liste : analyser l'état du site réel (absent / cassé / daté / moderne), estimer l'opportunité et le score d'obsolescence 0-100, écrire les colonnes Opportunite/Score/Signaux du CSV ia_echanges/<liste>/leads.csv. Zéro invention de fait — tout s'appuie sur le site réel ou les vraies données du lead. Déclencheurs : « qualifie les leads de la liste N », « score les sites », « état du site », « quelle opportunité », « mérite une refonte », « sans site », « site cassé », « site obsolète ». Complémentaire de ia-prospection (orchestrateur) et refonte-* (création/refonte de la page).
---

# qualify-leads — qualification / scoring des leads pour la prospection

Savoir-faire de jugement qui transforme un lead brut (déjà en base, et exposé dans
`ia_echanges/<liste>/leads.csv`) en **décision exploitable** : état du site, opportunité,
score d'obsolescence et signaux. C'est **ton** filtre métier pour décider **quoi prospecter**
et **avec quel angle** (refonte / création / correction).

> Dans ta machine, tu ne produis **pas** un CSV séparé « par cas » comme un export APIFY brut :
> tu travailles sur le CSV d'échange du dashboard (`ia_echanges/<liste>/leads.csv`) et tu écris
> **en place** les 3 colonnes IA de chaque ligne : `Opportunite`, `Score`, `Signaux`.
> Le dossier source de référence (mapping APIFY → colonnes, taux de remplissage) est rapatrié
> dans `references/colonnes-apify.md` pour mémoire.

---

## 1. Cadre : ce que tu dois produire

Pour **chaque ligne** du CSV (même `Id`, ne le touche jamais) :

| Colonne | Sens | Contenu |
|---|---|---|
| `Opportunite` | integer 0–100 | probabilité estimée que ce prospect devienne client (décision) |
| `Score` | integer 0–100 | **obsolescence du site** (0 = moderne, 100 = très daté / cassé) ; **vide** si pas de site analy sé |
| `Signaux` | texte court | le *pourquoi* : `non_responsive(+40); copyright 2019(+25)`, ou `Aucun site — forte opportunité`, etc. |

**Règle d'or** : on n'exclut plus personne sur l'état du site. Le site est une **aide à la décision**
et un **angle d'approche**. L'utilisateur décide via le dashboard.

---

## 2. Analyser l'état du site (déterministe)

Prérequis réseau : `requests` + `bs4` (déjà dans `requirements.txt`). Si `lxml` manque, `bs4`
peut utiliser `html.parser` ; privilégie `lxml` (installe-le si absent, demande avant).

### 2.1 Pas de site
`Site` vide (ou mort/404 confirmé) → `Score` vide, `Signaux` = `Aucun site — création`. C'est la
**meilleure opportunité** pour la pipeline « création de site web » (angle : proposer un site complet).

### 2.2 Site cassé (récupération HTTP)
Fetch `requests.get(site, timeout≈10, allow_redirects=True, UA navigateur réaliste)`, **1 retry**.
Classé `Site cassé` (`Score`=100, `Signaux`=cause) si :
- échec DNS / connexion refusée / timeout / boucle de redirections ;
- statut HTTP **≥ 400** ;
- page de **parking / domaine à vendre** (marqueurs : « for sale », « à vendre », sedoparking,
  afternic, hugedomains…).

> `http://` sans HTTPS ou cert TLS invalide ne classe **pas** « cassé » → +15 au score (signal `pas_https/cert`).

### 2.3 Score d'obsolescence (0–100) — signaux pondérés

| Signal | Points |
|---|---|
| Pas de `<meta name="viewport">` (non responsive — **signal n°1**) | **+40** |
| Copyright en pied < (année − 4) | **+25** |
| Stack obsolète (un seul suffit) : tables/frames, Flash/`.swf`, generator ancien (FrontPage/Jimdo/Joomla/Solocal/Wix), jQuery < 1.12, pas de charset utf-8 | **+20** |
| `pas_https` / cert invalide | +15 |
| Pas de favicon | +5 |
| Pas d'Open Graph | +5 |
| ≥ 5 images, aucune en WebP | +5 |

### 2.4 Libellé `Opportunite` + priorité

| État | Opportunite (colonne) | Angle pipeline |
|---|---|---|
| `Aucun site` | 5 (haut) | **création** (objectif web) |
| `Site cassé` | 4 | **refonte** (objectif web) |
| `Site daté` (score ≥ 40) | 3 | **refonte** |
| `Site à vérifier` (16–39) | 2 | refonte (vérifier visuellement) |
| `Site moderne` (≤ 15) | 1 (bas) | — (peu d'angle refonte) |
| non analysé | 0 | — |

> ⚠️ Le score est **faible sur la bande médiane** (16–39) : un site visuellement daté peut scorer bas,
> un site moderne peut monter. Les extrêmes (≥40 daté, ≤15 moderne) sont assez nets. En cas de doute,
> transmet « à vérifier » et laisse le jugement humain (ou couche 3 visuelle) trancher.

---

## 3. Écrire dans le CSV (en place, même `Id`)

Règles strictes du contrat `ia_echanges` :
1. **`Id` intouchable** — clé de raccordement. Ne jamais réordonner/réécrire une ligne.
2. Remplis `Opportunite`, `Score`, `Signaux` sur la même ligne, même `Id`.
3. **Zéro invention** : pas de faux chiffre, adresse, note, avis, coordonnée. Si tu ne peux pas
   juger (site injoignable sans cause nette), laisse vide + `Signaux` = ce que tu as observé.
4. CSV UTF-8, séparateur virgule ; une virgule ou retour-ligne dans un champ est protégé par guillemets.

---

## 4. Réintégration — NE FAIS PAS CE TRAVAIL

Une fois les colonnes remplies en place : **STOP**. Tu ne vas **jamais** en base, tu ne réordonnes
rien. Tu préviens l'utilisateur que c'est prêt, et il déclenche l'**Actualiser / scan** du dashboard
qui relit le CSV et réintègre `Opportunite/Score/Signaux` dans `leads_bruts`. Aucune action réseau
supplémentaire, aucun envoi.

---

## 5. Garde-fous

1. `Id` intouchable.
2. Zéro invention de fait.
3. L'état du site **informe** mais **n'exclut pas**.
4. Pas d'écriture silencieuse : colonne vide plutôt qu'une valeur au hasard.
5. Pas de scan / pas d'envoi : c'est le dashboard qui le fait après ta préparation.

---

## 6. Références

- `references/scoring-obsolescence.md` — règles détaillées du score (déterministe, reprise du savoir-faire).
- `references/colonnes-apify.md` — mapping des colonnes APIFY et taux de remplissage (mémoire du savoir-faire d'origine).