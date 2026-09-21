---
name: refonte-extraction
description: Savoir-faire d'EXTRACTION de la vérité d'un prospect (couleurs, images, textes RÉELS) pour préparer la création/refonte de sa page d'accueil dans la machine de prospection (D:\prospection-machine). Deux variantes : (1) AVEC site → rendu réel Playwright + analyse (render.py + analyze.py) sur le site du lead et output/clients/<slug>/asset-pack/ ; (2) SANS site (ou mort/404) → vérité extraite via Google Business, Instagram et WebArchive (vrais avis/notes, photos, textes, couleurs) pour construire le même asset-pack, sans rien inventer (missing_fields). Étape 1 de la chaîne refonte (→ refonte-design → refonte-build). Charge ce skill avant « extrais les assets du lead N », « récupère les vraies couleurs/images/textes », « prépare la refonte du lead N », « le client n'a pas de site ». Sortie : output/clients/<slug>/asset-pack (palette, images filtrées, textes réels, EXTRACTION-REPORT.md).
---

# refonte-extraction — extraire la vérité d'un lead (page ou entreprise)

Étape 1 de la chaîne refonte. Ton objectif : produire l'**asset-pack** d'un prospect avec les
**vraies** couleurs, images (filtrées anti-IA/anti-stock) et textes, **sans rien inventer**.

**Si la page finale doit convaincre un vrai client (qui paie gros), la vérité extraite EST l'argument.**
Un client se reconnaît dans SES photos, SES couleurs, SES textes — pas dans un template générique.

---

## 0. Cadre dans la machine

- Le lead vient du CSV `ia_echanges/<liste>/leads.csv` (colonne `Site`) ou de la base (`site_web`).
- Le dossier de travail client : `output/clients/<slug>/asset-pack/` (slug = domaine, `.`→`-`, sinon le nom du lead).
- La chaîne continue vers `refonte-design` puis `refonte-build`, qui copient la page finale dans
  `ia_echanges/<liste>/PROMPT/<IdLead>/index.html` + `capture.png` pour le dashboard.

**Brancher selon le cas** : si le lead a un site qui répond → section A (vrai site). Sinon → section B (vérité extraite).

---

## A. Cas « AVEC site » (site qui répond, même daté)

### A.1 Préparation
1. Déduis `<slug>` du domaine (ex. `https://plomberie-durand.fr` → `plomberie-durand-fr`).
2. Crée `output/clients/<slug>/asset-pack/`. Les sous-dossiers `raw/`, `screenshots/`, `images/`,
   `images-rejected/` sont créés par les scripts.

### A.2 Rendu réel de la page
```
python .claude/skills/refonte-extraction/scripts/render.py "<site>" output/clients/<slug>/asset-pack
```
Produit dans `raw/` (`rendered.html`, `computed-styles.json`, `dom-images.json`, `_render-meta.json`)
et `screenshots/` (`above-fold.png`, `full-page.png`).

- Erreur Python → corrige et relance (ne contourne pas).
- Si Playwright échoue (`PLAYWRIGHT_UNAVAILABLE` / `render_method=failed`) → fallback dégradé :
  `requests.get` du HTML brut dans `raw/rendered.html`, ou `WebFetch` pour au moins le texte.
  Note `render_method` dans `_render-meta.json`. **Ne jamais lancer `playwright install` sans demander.**

### A.3 Analyse : couleurs + images + texte
```
python .claude/skills/refonte-extraction/scripts/analyze.py output/clients/<slug>/asset-pack
```
Produit : `colors.json` (`palette_for_design` + dominantes + confidence), `images/` + `images-rejected/`
+ `images-manifest.json`, `content.json` + `content.md`, `meta.json`, `EXTRACTION-REPORT.md`.

Même règle : erreur Python → corrige et relance.

---

## B. Cas « SANS site » (ou mort/404) — VÉRITÉ EXTRAITE

Il n'y a pas de site à extraire : la vérité du client vit ailleurs. Tu **cherches et collectes** ses
vraies traces numériques pour construire le même asset-pack. **Rien inventé** : tout trou → `missing_fields`.

### B.1 Google Business (la première source de vérité)
`WebSearch`/`WebFetch` : `"<nom> <ville>"`, `"<nom> <ville> google business"`, `"<nom> google reviews"`.
Collecte (réel, vérifiable) :
- nom exact, adresse, téléphone, horaires ; catégorie de la fiche ;
- **note Google et nombre d'avis** (preuve sociale réelle) ;
- **avis réels verbatim** (1-3) — preuve exploitable dans la page ;
- photos uploadées (logo, produits, locaux).

### B.2 Instagram / réseaux
`WebSearch` : `"<nom> <ville> instagram"`. Collecte : vraies photos de travaux/produits, couleurs de
marque, ton de la bio, vrai slogan si présent. Priorise les images exploitables (non IA, non stock).

### B.3 WebArchive (reliques si le site est juste 404)
Si un ancien site est visible sur `web.archive.org` : récupère les vraies couleurs/textes d'origine via
`WebFetch` sur l'iframe archive. C'est de la vérité récupérable, pas de l'invention.

### B.4 Construction du dossier (identique à A)
Crée `output/clients/<slug>/asset-pack/` avec :
- `colors.json` — `palette_for_design` déduite des vraies couleurs trouvées (logo/fiche GMB/Instagram) + `confidence`.
- `images/` — vraies images collectées (filtrées : pas d'IA suspectée, pas de stock marqué).
- `content.json` + `content.md` — textes réels (description GMB, bio Instagram, services si listés) + `missing_fields`.
- `meta.json` + `EXTRACTION-REPORT.md`.

> Cas `site_status` ∈ {`broken_404`, `unreachable`, `empty_shell`} : produis toujours un asset-pack
> **balisé** (missing_fields complet), ne plante pas. Si tu ne trouves rien → le build utilisera des
> placeholders visibles, qui deviennent la liste de questions à poser au client.

---

## C. Restitution (commun aux deux cas)

Donne un résumé court : chemin du dossier client, statut du site (`Aucun site`/`Site cassé`/`Site daté (N)`/
`Site moderne (N)` pour mémoire), palette (`palette_for_design`), nombre d'images gardées/écartées,
liste des `missing_fields`. Termine par : **« prêt pour refonte-design »**.

**Rappel** : tu n'inventes aucune donnée. Tout ce qui manque est `ABSENT` / dans `missing_fields` —
ce sont les trous que le build transformera en placeholders visibles = matière d'appel et d'upsell client.