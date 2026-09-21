# Analyse de l'état du site & score d'obsolescence

Implémenté dans `scripts/qualify.py` (`analyze_site`). **L'état du site n'exclut plus aucun lead** :
il sert uniquement à **qualifier l'opportunité** (`Opportunité` + `Score` + `Signaux`) et à **trier**
le fichier `prospects.csv`. C'est l'utilisateur qui décide quoi prospecter.

## Pas de site
`website` vide → `Opportunité = Aucun site`, `Score` vide. Meilleure opportunité → **tout en haut** du tri.

## Site cassé (récupération HTTP)
Fetch via `requests` : timeout ~10 s, **1 retry**, User-Agent navigateur réaliste, suit les redirections.
Cas → `Opportunité = Site cassé`, `Score` vide, **haut du tri** :
- échec DNS / connexion refusée / timeout / boucle de redirections ;
- statut HTTP **≥ 400** ;
- page de **parking / domaine à vendre** (marqueurs « for sale », « à vendre », sedoparking, afternic, hugedomains…).

`http://` sans HTTPS **ou** certificat TLS invalide ne classe pas « cassé » → **+15** au score (signal `pas_https/cert`).

## Site daté techniquement (score 0-100, via BeautifulSoup)

| Signal | Points |
|---|---|
| Pas de `<meta name="viewport">` (non responsive — **signal n°1**) | **+40** |
| Copyright en pied < (année − 4) | **+25** |
| Stack obsolète (un seul suffit) : tables/frames de mise en page, Flash/`.swf`, generator ancien (FrontPage/Jimdo/Joomla/Solocal/Wix), jQuery < 1.12, pas de charset utf-8 | **+20** |
| `pas_https` / cert invalide | +15 |
| Pas de favicon | +5 |
| Pas d'Open Graph | +5 |
| ≥ 5 images, aucune en WebP | +5 |

Le détail des signaux déclenchés est exposé tel quel dans la colonne **`Signaux`** de `prospects.csv`,
pour que l'utilisateur comprenne *pourquoi* un site est jugé daté.

### Du score au libellé `Opportunité` (et au tri)
Le score n'est plus un seuil d'inclusion/exclusion — il alimente le **libellé** et la **priorité de tri** :

| Score | Opportunité | Rang de tri |
|---|---|---|
| (pas de site) | `Aucun site` | 5 (haut) |
| (site cassé) | `Site cassé` | 4 |
| **≥ 40** | `Site daté (N)` | 3 — du plus daté au moins daté |
| **16-39** | `Site à vérifier (N)` | 2 |
| **≤ 15** | `Site moderne (N)` | 1 (bas) |
| (mode `--no-fetch`) | `Non vérifié` | 0 |

> ⚠️ Le score est un signal **faible** sur la tranche médiane : des sites visuellement très datés
> scorent parfois bas (ex. typo Times + Google+ mort = 25) et des sites modernes montent à 40.
> C'est exactement la bande `Site à vérifier (16-39)` que la **Couche 3** va regarder pour trancher ;
> les extrêmes (`Site daté ≥40`, `Site moderne ≤15`) sont jugés assez nets pour se fier au seul HTML.
> Et dans tous les cas, on **n'exclut plus** : tout reste dans `prospects.csv`.

## Couche 3 — vérification visuelle (bande `Site à vérifier` uniquement)
Hors script, **pilotée par Claude** (voir le SKILL.md). Pour chaque site unique étiqueté `Site à vérifier`,
Claude capture des screenshots (mobile + desktop) via Playwright puis **juge visuellement**.

**Biais permissif** : on ne tranche « moderne » qu'un site **clairement récent et entretenu** (design
contemporain, responsive, palette/typo actuelles, espace blanc). Au moindre signal d'obsolescence —
copyright vieilli, template daté, stack ancien, rendu mobile bancal, liens vers services morts (Google+…) —
ou **en cas de doute → daté**.

La vision **ne supprime jamais** un lead : elle réécrit seulement le libellé `Opportunité` des lignes
concernées (et de toutes les lignes du même établissement) en `Site daté (vu)` ou `Site moderne (vu)`.
Le suffixe `(vu)` distingue « jugé sur capture » des libellés inférés du seul HTML. On re-trie ensuite avec
`python3 scripts/qualify.py --resort output/prospects.csv`.

## Points de réglage connus
- **Wix** dans la liste « builder ancien » : le `<meta generator>` ne distingue pas un vieux Wix
  d'un Wix moderne responsive. Un Wix moderne (viewport présent) atterrit souvent en `Site à vérifier`
  (≈25) — sans conséquence puisqu'il reste dans la sortie. À retirer de la liste s'il gonfle à tort le score.
- Les seuils 15/40 ne filtrent plus rien : ils ne déplacent qu'un lead entre les libellés
  `Site moderne` / `Site à vérifier` / `Site daté` et donc sa position dans le tri.
