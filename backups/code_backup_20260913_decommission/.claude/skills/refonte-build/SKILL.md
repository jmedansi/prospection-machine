---
name: refonte-build
description: Savoir-faire de CÉATION/BUILD de la page d'accueil HTML finale d'un lead, à partir des SEULS vrais assets (DESIGN.md + asset-pack), pour la machine de prospection (D:\prospection-machine). Étape 3 (finale) de la chaîne refonte, APRÈS refonte-design. Code une page self-contained qui VEND (copywriting sous contrainte « zéro fait inventé »), puis dépose le résultat au format dashboard : ia_echanges/<liste>/PROMPT/<IdLead>/index.html + capture.png. Charge ce skill pour « build la page », « code le index.html », « génère la maquette finale », « page du lead N ». La page se montre telle quelle au prospect (cold email / appel). Sortie : output/clients/<slug>/site/index.html + BUILD-NOTES.md, et la copie dans le PROMPT/<IdLead>/.
---

# refonte-build — coder la page finale (vendeuse, zéro fait inventé)

Étape 3 (finale) de la chaîne refonte. Tu codes la nouvelle page d'accueil du lead en n'utilisant
**que** les assets réels extraits. **C'est elle qu'on montre au prospect** — elle doit donner envie
d'acheter, pas décrire.

**Règle d'or (à relire avant chaque ligne)** : le wording peut **reformuler le réel**, jamais
**affirmer un nouveau fait vérifiable**. Dans le doute → placeholder `[À COMPLÉTER : …]`.

---

## Dossier de travail & entrées

- Dossier client : `output/clients/<slug>/` (remplace `<slug>`).
- Entrées (lis-les d'abord) :
  - `output/clients/<slug>/docs/DESIGN.md` (tokens : couleurs, fonts + URL Google Fonts, spacing, radius, motion).
  - `output/clients/<slug>/asset-pack/content.json` + `content.md` (textes réels + `missing_fields`).
  - `output/clients/<slug>/asset-pack/images-manifest.json` (images : **uniquement** `status: kept`).
  - `output/clients/<slug>/asset-pack/colors.json` (palette de référence).
- **Si `docs/DESIGN.md` n'existe pas : arrête-toi** → lance `refonte-design` d'abord.

## Sortie (2 niveaux)

1. **Travail** : `output/clients/<slug>/site/index.html` (1 fichier self-contained) + `site/assets/`
   (images copiées) + `site/BUILD-NOTES.md`.
2. **Dashboard (obligatoire pour la machine)** : copie la page et sa capture dans
   `ia_echanges/<liste>/PROMPT/<IdLead>/` :
   - `ia_echanges/<liste>/PROMPT/<IdLead>/index.html` = la page buildée.
   - `ia_echanges/<liste>/PROMPT/<IdLead>/capture.png` = capture plein écran de la page (Playwright).
   > <liste> et <IdLead> viennent du CSV `ia_echanges/<liste>/leads.csv` (colonne `Id`). C'est ce que
   > le dashboard affiche dans le panneau latéral.

## Stack
HTML statique + Tailwind Play CDN (`<script src="https://cdn.tailwindcss.com"></script>` + `tailwind.config`
inline), fonts via `<link>` Google Fonts, tokens du `DESIGN.md` branchés dans `tailwind.config`.

## Structure de la page (narration compacte qui vend)
1. **Hero** — headline value-prop (exprime la « memorable thing » de `DESIGN.md` via une formule) +
   sous-titre + **CTA fort** + image hero réelle.
2. **Barre de preuve** — *uniquement si une preuve réelle existe* (ex. « 34 avis Google ★ », nombre de
   projets réel, extraits d'avis GMB). Sinon placeholder/omission — jamais de chiffre inventé.
3. **Services en bénéfices** — chaque service reformulé en bénéfice client (pas un titre nu).
4. **Preuve / À propos** — témoignage réel verbatim (GMB/Instagram), ou `[À COMPLÉTER]`, jamais un faux avis.
5. **CTA final** — récapitule la valeur + répète le CTA.
6. **Footer** — mentions réelles (copyright…).

Reprends la direction `DESIGN.md` et adapte le **registre** à sa personnalité. Images : hero = `role_guess:
hero` du manifeste ; dépriorise `ai_uncertain: true` (dernier recours).

## Copy (principes)
- **Bénéfices > features** ; **Clarté > esprit** ; **Spécificité issue du réel uniquement** ;
  **Voix active + CTA fort** (`[verbe] + [ce qu'on obtient]`) ; **Une idée par section** ; **Registre adapté à DESIGN.md**.
- Formules headline, narration, exemples autorisés/interdits : lis **`references/copy-refonte.md`**.

## Règles ANTI-HALLUCINATION (non négociables)
1. **Whitelist stricte.** La page ne référence que des fichiers présents dans `asset-pack/images/` et
   du texte de `content.json`/`content.md`. Interdit : `<img>` externe, image stock, image générée,
   icône/logo inventé, image placeholder.
2. **Placeholders visibles** : tout champ `missing_fields` / slot sans donnée → bloc voyant
   `<span class="placeholder">[À COMPLÉTER : …]</span>` (fond `#FEF3C7`, bordure pointillée, petit label).
3. **Zéro invention de FAITS, réécriture du FRAMING autorisée** :
   - FAITS verrouillés : chiffres, dates, ancienneté, prix, notes, nb d'avis/clients/projets,
     témoignages (texte+noms), coordonnées, noms propres, périmètre des services. Jamais inventés.
   - FRAMING libre : headline, sous-titre, angle des services, libellés CTA, narration — sous la règle d'or.
4. **Pas d'image hero comblée** : si aucune photo hero réelle → hero en bloc couleur/typo + `[À COMPLÉTER]`.
5. **Self-check final** : grep `lorem`, `unsplash`, `placeholder.com`, `picsum`, tout chiffre non sourcé ;
   vérifie chaque ligne réécrite n'introduit aucun fait absent de `content.json` ; grep les AI-tells
   (« At its core », « In today's », « Let's delve into », etc.) et points d'exclamation marketing.
6. **`BUILD-NOTES.md`** : (a) images réelles utilisées, (b) placeholders = demandes au client,
   (c) écarts vs DESIGN.md, (d) copy retravaillée `original → réécrit → formule`.

## Fin
1. Capture la page en `capture.png` (Playwright, plein écran) →
   `ia_echanges/<liste>/PROMPT/<IdLead>/capture.png`.
2. Copie la page en `ia_echanges/<liste>/PROMPT/<IdLead>/index.html`.
3. Ouvre le résultat (`start output/clients/<slug>/site/index.html`).
4. (Option) Screenshot avant/après (côté à côté) → contenu d'email upsell.
5. Restitue : chemin, placeholders (= demandes client), résultat du self-check, et la confirmation
   que le PROMPT/<IdLead>/ est prêt pour le scan dashboard.