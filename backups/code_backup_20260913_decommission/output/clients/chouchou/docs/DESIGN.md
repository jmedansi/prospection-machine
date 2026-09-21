# DESIGN.md — Chouchou (restaurantchouchouparis.fr)

## Product Context
Restaurant « Chouchou » à Paris : **cuisine orientale et française**, positionnement **haut de gamme**,
escapade culinaire avec signature **tiramisu**. Cible : clientèle qui cherche une table raffinée,
une expérience « haut de gamme » et un dessert signature. Site actuel daté, pas de réservation en ligne.

## Memorable thing
« Une cuisine gallo-orientale haut de gamme à Paris, servie avec un tiramisu signature. »

## Aesthetic Direction
**Luxury/Refined + warm editorial.** Base foncée chaleureuse, accent orange vif, photos réelles plein cadre,
typographie serif élégante en display, beaucoup d'air, section « plat signature » mise en scène. Registre :
raffiné, sensuel, français.

## Color (verrouillée — `palette_for_design`)
| Token | Hex | Rôle |
|---|---|---|
| `--primary` | `#FF5733` | Accent de marque (CTA, détails) |
| `--on-primary` | `#FFFFFF` | Texte sur l'accent |
| `--neutral-dark` | `#19100C` | Fond sombre, sections |
| `--neutral-warm` | `#50382A` | Ton chaud (sur-titres, teintes) |
| `--neutral-light` | `#F4F4F4` | Fond clair, cartes |
| `--ink` | `#1C1917` | Texte principal sur clair |
| `--muted` | `#6B6259` | Texte secondaire |
| `--placeholder-bg` | `#FEF3C7` | Fonds des placeholders `[À COMPLÉTER]` |
`secondary` était `null` → dérivée des ombres foncées du primary (#C23F1E, #A63315). Confidence: high.

## Typography
- **Display** : `Fraunces` (600–700, serif food/elegant) — headline, titres de section.
- **Body** : `Instrument Sans` (400–600) — paragraphes, navigation.
- Aucune typo de marque volontaire détectée dans `raw/computed-styles.json` → droit de choisir.

## Spacing
Échelle base 8 : `4,8,12,16,24,32,48,64,96,128`. Section padding vertical `py-24 md:py-32`.

## Layout
- Hero plein écran (image réelle full-bleed) + surimposition sombre dégradé + headline + CTA.
- Barre d'ancrage discrète (carte / spécialités / contact).
- Section « Un trophée de prestige » (positionnement haut de gamme).
- Spécialités en bénéfices (3 cartes).
- Section **signature tiramisu** mise en scène (image + copy).
- À propos + force des vins, spa du Chef.
- CTA final sombre + footer.
- Placeholders visibles `[À COMPLÉTER : …]` pour About/Horaires/Témoignage.

## Motion
`motion-motion-preset-fades` (intentional) : fade-in au scroll, hover doux sur cartes/CTA, image hero fixe (parallax léger).

## Decisions Log
- D1 (build) : images réelles `kept` de `asset-pack/images/` ; hero = `img-002.jpg` (role_guess hero).
  Images copiées dans `site/assets/` et dans `PROMPT/5/assets/` pour rester self-contained.
- D2 (build) : aucune donnée de preuve (« avis Google », chiffres) extractible → section preuve omise,
  remplacée par le positionnement « Trophée de Prestige » (titre extrait, reformulé, aucun chiffre).
- D3 (build) : About/Horaires/Témoignages absents (`missing_fields`) → placeholders visibles `[À COMPLÉTER]`.