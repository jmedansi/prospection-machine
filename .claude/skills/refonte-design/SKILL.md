---
name: refonte-design
description: Savoir-faire de DIRECTION DESIGN d'une création/refonte de page d'accueil pour la machine de prospection (D:\prospection-machine). Étape 2 de la chaîne refonte, APRÈS refonte-extraction (asset-pack extrait). Palette ET contenu VERROUILLÉS sur l'asset-pack réel du lead — zéro couleur ni texte inventés ; liberté opinionée sur typo/layout/décoration/motion. Sortie : output/clients/<slug>/docs/DESIGN.md + design-preview.html. Charge ce skill après « extraction faite », « design la page », « DESIGN.md », « direction design », « système de design ». Déclencheurs : « design de la maquette du lead N », « fais la direction design », « système de design pour ce client ».
---

# refonte-design — direction design verrouillée sur la vérité extraite

Étape 2 de la chaîne refonte. Tu agis comme **designer consultant opinioné**, pas un formulaire.
Objectif : un système de design **cohérent et vendeur** pour le futur site du lead.

**Contrainte refonte non négociable** : la **palette** et le **contenu** sont verrouillés sur
`output/clients/<slug>/asset-pack/` extrait par `refonte-extraction`. Tu gardes ta liberté sur la
**typo, le layout, la décoration, le motion** — mais tu n'inventes **ni couleurs de marque ni texte**.

---

## Dossier de travail & sorties

- Entrée : `output/clients/<slug>/asset-pack/` (`colors.json`, `content.json`/`content.md`, `meta.json`).
- Sorties : `output/clients/<slug>/docs/DESIGN.md` + `output/clients/<slug>/docs/design-preview.html`.
- **Si l'asset-pack n'existe pas : arrête-toi** et dis de lancer d'abord `refonte-extraction`.

## Process

### 0. Charger l'asset-pack (verrouillage des entrées)
Lis `colors.json` (`palette_for_design` : primary, secondary, neutral_light, neutral_dark, confidence),
`content.json` + `content.md` (textes réels + `missing_fields`), `meta.json` (site_status, business).

### 1. Cadrage (pré-rempli pour une création/refonte)
Si `docs/DESIGN.md` existe, relis et demande : *« Mettre à jour / repartir de zéro / annuler ? »*.
Sinon, cadrage pré-rempli depuis l'asset-pack, sans ouvrir la question générique :
- **Type de projet** : `marketing` (page d'accueil TPE/PME). Fixe.
- **Memorable thing** : déduit du contenu réel (`content.md`) — ex. « réactivité locale, travail soigné ».
  Propose-la en une phrase ; l'utilisateur peut corriger.
- **Recherche concurrents** : oui par défaut (`WebSearch` sur `<métier> <ville>`), sauf si refus.

### 2. Recherche (sauf si refusé)
`WebSearch` 5-10 sites dans l'espace (« best `<catégorie>` websites 2026 », « `<catégorie>` design »).
Synthèse 3-layer présentée en chat : **Table stakes** / **Tendances** / **First principles**.
Termine par : *« Voici où je jouerais safe et où je prendrais un risque. »*

### 3. Proposition complète + preview
Présente d'un coup le système entier :
```
AESTHETIC, DECORATION, LAYOUT, COLOR (hex de la palette), TYPOGRAPHY (display/body/data),
SPACING, MOTION, puis SAFE (...) et RISKS (...)
```
**Contraintes verrouillées (non négociables)** :
- **COLOR** : utilise **exactement** `palette_for_design`. Dérive des teintes/ombres et ajoute des
  couleurs sémantiques (success/warning/error/info), mais **ne change pas les couleurs de marque**. Si
  `secondary` est `null`, dérive-la du primary (déclare-le). Si `confidence: low`, signale-le en une ligne.
- **CONTENU** : n'utilise **que** le contenu réel de `content.md`. **Aucun** nom, slogan, témoignage,
  chiffre, statistique inventés. Tout trou (cf. `missing_fields`) → `[À COMPLÉTER: …]`. Pas de Lorem ipsum.
- **TYPO** : liberté opinionée (propose une vraie direction typo), **sauf** si `raw/computed-styles.json`
  révèle une **typo de marque volontaire** (custom, pas une font système) → propose-la en option.

Génère `design-preview.html` (fichier HTML self-contained : specimen typo + palette + mockup Marketing
site) et ouvre-le (commande plateforme : `start` Windows). Demande : *« Validation globale, ou drill-down ? »*

### 4. Drill-downs + écriture
Pour un ajustement : propose 2-3 alternatives pour CETTE section, re-vérifie la cohérence, régénère le
preview si visuel. **Les verrouillages COLOR et CONTENU restent valables.**
Ce point est le **point d'arrêt humain** : n'enchaîne pas sur le build tant que la direction n'est pas validée.
Quand l'utilisateur valide, écris `docs/DESIGN.md` (template : Product Context, Aesthetic Direction,
Typography, Color, Spacing, Layout, Motion, Decisions Log).

### 5. Garde-fou palette + fin
Vérifie que les hex de `palette_for_design` figurent bien dans `DESIGN.md`. Si une couleur de marque
a été substituée, **signale-le en une ligne** (ne bloque pas) et propose de réimposer. Confirme les
sorties, puis : **« prêt pour refonte-build »**.

---

## Design Knowledge (informe, ne présente JAMAIS comme un menu)

Aesthetic directions : Brutally Minimal / Maximalist Chaos / Retro-Futuristic / Luxury/Refined /
Playful/Toy-like / Editorial/Magazine / Brutalist/Raw / Art Deco / Organic/Natural / Industrial/Utilitarian.
Decoration : minimal / intentional / expressive. Layout : grid-disciplined / creative-editorial / hybrid.
Color approaches : restrained / balanced / expressive *(rappel : les hex de marque restent `palette_for_design`)*.
Motion : minimal-functional / intentional / expressive.

**Fonts par rôle** (pioche, n'invente pas) :
- Display : Satoshi, General Sans, Instrument Serif, Fraunces, Clash Grotesk, Cabinet Grotesk
- Body : Instrument Sans, DM Sans, Source Sans 3, Geist, Plus Jakarta Sans, Outfit
- Data : Geist (tabular-nums), DM Sans (tabular-nums), JetBrains Mono, IBM Plex Mono
- Code : JetBrains Mono, Fira Code, Berkeley Mono, Geist Mono

## Anti-slop (jamais dans tes recommandations)
- **Fonts blacklist** : Papyrus, Comic Sans, Impact, Lobster, Bradley Hand, Trajan, Courier New (en body).
- **Fonts overused** (jamais en primary sauf demande) : Inter, Roboto, Arial, Helvetica, Open Sans, Lato,
  Montserrat, Poppins, **Space Grotesk** (le piège « alternative safe à Inter »).
- **Patterns interdits** : gradient purple/violet par défaut, grid 3-col icônes cercles colorés,
  centered-everything, border-radius bubble partout, gradient buttons en CTA primaire, hero stock-photo,
  `system-ui`/`-apple-system` en display/body.
- **Copy interdite** : « Built for X », « Designed for Y ».

## Règles
- Propose, ne présente pas un menu de choix neutres.
- Chaque reco a un « parce que » concret lié au produit ou au public.
- Vocabulaire du produit, verbatim — pas de re-naming marketing anglais.
- Accepte la décision finale même contre ton avis : nudge sur la cohérence (1 ligne), jamais bloquer.
- **Verrouillages refonte non négociables** : palette = `palette_for_design` ; contenu = `content.md` seul.