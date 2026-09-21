# BUILD-NOTES.md — Clinique George V (cg5.fr) · lead 7134

Étape 3/3 de la chaîne refonte. Page finale vendeuse, zéro fait inventé.
**v2 — art direction « premium »** : reconstruction complète (motion + éditorial typographique).

## (v2) Ce qui a changé vs v1
- **Art direction** : hero éditorial à double image (collage photo, cadres offset), labels verticaux,
  titres Fraunces géants (jusqu'à 5.3rem), chiffres « 69 » en watermark, quote avec drop-cap, filets hairline.
- **Motion** : reveals au scroll (IntersectionObserver + délais stagger), images révélées par clip-path,
  parallaxe douce (rAF + lerp) sur 7 images, marquee de preuve, header qui se condense au scroll,
  portraits praticiens **N&B → couleur** au survol, accordéons pôles animés (grid-template-rows).
- **Contenu réseau** : les 3 pôles dépliés en accordéons avec la liste complète verbatim
  (`services_detail`) ; barreur de preuve ; livre d'or asymétrique (1 grande citation + 8 avis).
- **Fondations** : JSON-LD `MedicalClinic` (adresse/téléphone/horaires réels), meta description,
  grain cinéma SVG, sélection personnalisée, `prefers-reduced-motion` respecté, aria-expanded sur accordéons.
- Les 8 placeholders restants sont les seules données absentes du site (email, liens, légal).

## (a) Images réelles utilisées (`site/assets/`)
| Asset | Source | Rôle |
|---|---|---|
| img-001.png | clinique-george-v.png (hébergement) | Hero — hôtel particulier |
| img-006.jpg | photo-site.jpeg | Section À propos |
| img-002.jpg / img-004.jpg / img-005.jpg | portraits Dr (site) | Praticiens Drossard / Julienne / Garreau |
| img-009.jpg / img-010.jpg | photos réelles | Section Histoire |
| img-011.jpg | photo soin visage | Pôle médecine esthétique |
| img-008.jpg | Soirée Blanche | Band Actualités |
| img-012.jpg | consultation | Band Actualités |
| brand/img-003.svg | logo Doctolib | Preuve de prise de RDV en ligne (CTA final) |

Non reprises : img-007 (capture d'écran), img-013 (fonds stock `ai_uncertain`).

## (b) Placeholders = demandes client
1. **Adresse email** (footer) — `contact.email` absent du site (`missing_fields`).
2. **Lien Doctolib** — le logo existe mais l'URL de booking n'a pas été extraite.
3. **Lien actualités** — sections réelles « Protocoles Péri-opératoires » / « Bioma Therapy™ » sans URL.
4. **Légende** consultation (img-012) — visuel réel sans texte associé.
5. **Formulaire newsletter** — mécanisme d'inscription à brancher.
6. **Mentions légales** — non extractibles.
7. **Année de copyright** — non extraite du site.

## (c) Écarts vs DESIGN.md
- Palette/tons : conformes (primary `#191E23`, secondary/s `#2B3238`, filets `fl` `#CFCDCE`, textes `nd` `#4B454A`).
- Typographies : Fraunces (display) + Instrument Sans (body) + DM Sans (data) — conformes.
- Structure : conforme au plan (hero / preuve / à propos / pôles / praticiens / histoire / actualités / avis / CTA final / footer).
- Les 9 avis Google sont affichés verbatim (truncation « … » pour les plus longs, au point de coupe exact) ; ordre de l'extraction conservé sauf mise en avant de l'avis Sarah Slous et de la 6e carte (Marie Picault) — sélection éditoriale, aucun texte modifié.
- Hero sans photo par-dessus laquelle une photo serait requise : photo réelle de l'hôtel particulier utilisée.

## (d) Copy retravaillée `original → réécrit → formule`
1. `Chirurgie et médecine esthétique et reconstructrice sur Bordeaux` → **« La beauté qui ne vieillit pas. »** — formule « memorable thing » de DESIGN.md (Bacchus & Apollon : seuls dieux à ne pas vieillir). Aucun fait nouveau.
2. Sous-titre = verbatim `subheadline` (ville + périmètre Gironde).
3. Pôle Chirurgie → bénéfice **« Se réconcilier avec son image. »** — reformule `poles_intro` réel (« besoin de se réconcilier avec son image »).
4. Pôle Médecine → **« Le raffinement des méthodes, dans la mesure. »** — issu du credo (« méthodes et techniques de plus en plus raffinées ») + french touch (« dans la mesure »).
5. Pôle Épilation → **« Des résultats nets, reconnus par nos patientes. »** — issu de l'avis Ambre Gennari (« je vois de net résultats ») + avis DUBEAU (efficacité de l'épilation).
6. Intro des pôles : reformulation du passage réel « se réconcilier avec son image / problèmes intimes / écoute et empathie / pratique hospitalière intensive ».
7. CTA `cta_found = Contact / Rendez-vous / Prendre un RDV` → « **Prendre rendez-vous** » (lien `tel:+33535549727`, numéro réel).

## Self-check
- Aucun `lorem`/`unsplash`/`picsum`/`placeholder.com`/`pixel` ; aucune IA-tell (seamless, innovant, etc.).
- Seuls faits chiffrés : **69 avis**, **EXCELLENT** (Google), **3 pôles**, **3 praticiens** — présents dans `content.json`.
- Tous les `<img>` référencent des fichiers présents dans `site/assets/` (12 références vérifiées).
- Textes des biographies, histoire, credo, french touch, horaires, adresse, téléphone : verbatim de `content.json`.