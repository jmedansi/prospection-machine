# DESIGN.md — Clinique George V (cg5.fr)

> Étape 2/3 de la chaîne refonte. Contrat de design à respecter **strictement** par tout agent build.
> Contenu **100 % verbatim** de `asset-pack/content.json` / `content.md`. Aucune couleur, aucun texte inventé.
> Champs absents → placeholder `[À COMPLÉTER : …]`.

## Inputs (extraction terminée, confidence high)
- `output/clients/cg5-fr/asset-pack/content.json` — tout le contenu réel.
- `output/clients/cg5-fr/asset-pack/images-manifest.json` — **13 images** `status: kept` à utiliser.
- `output/clients/cg5-fr/asset-pack/colors.json` — palette auditée (confidence high).
- Source : `raw/rendered.html` (225 Ko). Note Google EXCELLENT — 69 avis.

## Décision de design
- **Aesthetic** : `Luxury/Refined` — clinique premium à l’ADN bordelais (maison de vins, mascaron Bacchus).
- **Layout** : `editorial-creative` — image photojournalistique, aération éditoriale, hiérarchies typographiques fortes.
- **Vibe** : sobre, élégant, confiance médicale. Accent sur le récit « sans âge » (Bacchus & Apollon) et la preuve sociale Google.

## Palette (verrouillée)
| Role | Hex | Usage |
|---|---|---|
| Primary | `#191E23` | fonds hero / avis, CTA texte |
| Secondary | `#2B3238` | cartes, fonds de section |
| Neutral light | `#FFFFFF` | fond principal, texte sur primary |
| Neutral dark | `#4B454A` | textes secondaires, low-priority |
| Accent | `#CFCDCE` | filets, numéros de sections, utilitaires |

## Typographie
- **Display** : `Fraunces` (300/400/500 + italique) — titres, citations longues, chiffres emblématiques.
- **Body** : `Instrument Sans` (400/500/600) — paragraphes, navigation, CTA.
- **Data** : `DM Sans` (400/500, tabular-nums) — horaires, notes, labels techniques.

## Iconographie
- Sélection **vectrice** (icons lucide-style, trait 1.5) : guide, médecin, sparkle, calque, snowflake, cloche, comb, fleur, drop, éclair, soleil, zapsolde, heart, mallette, anneau, piston, pin, phone, clock, home, mail.
- Impossibles à vérifier/garantir côté client → `[À COMPLÉTER : …]`.

## Structure de page (approuvée)
1. **Header** : logo (img-003, SVG Doctolib → à remplacer par identité/monogramme George V), nav, CTA Rendez-vous + 05 35 54 97 27, bandeau Google EXCELLENT · 69 avis.
2. **Hero** : headline verbatim + sous-texte services Bordeaux/Gironde + CTA RDV + img-001 (hôtel particulier) + horaires.
3. **À propos** : paragraphe verbatim + img-006 + note Google.
4. **Pôles** (01/02/03) : chirurgie esthétique, médecine esthétique, épilation définitive + intro verbatim pôle 1 + credo.
5. **Histoire / emblème** : texte Bacchus/Apollon + french touch (citation) + img-009/img-010.
6. **Praticiens** : 3 dossiers (Dr Drossard, Dr Julienne, Dr Garreau) — nom, spécialité, bio verbatim, CTA RDV. Photos img-002/004/005 disponibles.
7. **Livre d’or** : avis Google verbatim (9) sur fond `#191E23`, note EXCELLENT · 69 avis.
8. **Footer** : contact (163 Bd George V 33400 Talence · 05 35 54 97 27), horaires, newsletter, mentions `[À COMPLÉTER : …]`.
9. **Flottant** (optionnel) : CTA RDV sticky mobile + bandeau cookies `[À COMPLÉTER : politique]`.

## Services (contenu réseau, détail)
Détail complet par catégorie dans `content.json > services_detail` (chirurgie : visage/seins/silhouette/cheveux/intime ; médecine : hyaluronique/botox/radiesse/cryolipolyse/hifu/hydrofacial/lasers/microneedling/peelings/LED/bloomea ; espace bien-être : coach/facialiste/sexologue ; épilation définitive). Dépliage au clic, sans inventer de texte.

## Composants
- **Bouton primaire** (`--p`, radius-full, hover translateY-1px), **secondaire** (`--fl`), **lien souligné** data.
- **Carte pôle** : numéro `.num` data + disp titre + liste services.
- **Bloc praticien** : grille éditoriale, photo portrait (img-002/004/005), bio verbatim.
- **Citation avis** : `disp` italique, auteur en `data` small caps.
- **Filets** `--fl` : séparation éditoriale (divide-y, hairline).

## Accessibilité & perf
- Contraste : textes ≥ `#4B454A` sur fond blanc (≥ 4.6:1) ; `#CFCDCE` uniquement pour décoration.
- Images : `alt` descriptifs, `loading="lazy"` hors hero, `width/height` natifs.
- Fonts : google fonts (Fraunces + Instrument Sans + DM Sans), fallback system.
- Mobile-first, single-column jusqu’à 640 px ; grille md: ensuite.
- Pas de tracking, pas de JS lourd : accordéons details/summary.

## Images (13 kept — manifest)
img-001 clinique-george-v (hero/carte) · img-002 Dr Drossard · img-003 logo Doctolib (brand) · img-004 Dr Julienne · img-005 Dr Garreau · img-006 photo-site · img-007 capture écran (preuve social, éviter) · img-008 Soirée Blanche · img-009 · img-010 photos réelles · img-011/-012/-013 fonds stock (décoration sobre).

## Livrables build (étape 3)
`index.html` autonome (Tailwind CDN v4 browser + Google Fonts + CSS custom) + `capture.png` (Playwright 1440×900) → copie dans `D:\prospection-machine\ia_echanges\liste_139\PROMPT\7134\`.

## Non-goals
- Ne jamais réutiliser les 9 images rejetées.
- Ne pas inventer d’email, de tarifs, d’adresse secondaire, de mentions légales.
- Ne pas intégrer la capture d’écran tel quel comme preuve de social (consumable à éviter).