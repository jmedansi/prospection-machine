# BUILD-NOTES — Chouchou

## (a) Images réelles utilisées
- `assets/hero-chouchou.jpg` = `asset-pack/images/img-002.jpg` (2 048×1 366, `role_guess: hero`, kept, sharp)
- `assets/table.jpg` = `asset-pack/images/img-003.jpg` (kept)
- (img-009 « plat signature » conservée comme azimut pour un futur remplacement hero, non montée dans cette passe)

## (b) Placeholders = demandes au client
1. Nature / nom du « Trophée de Prestige » (titre extrait, aucun chiffre disponible).
2. Description détaillée du tiramisu signature.
3. Histoire / « à propos » de la maison (texte réel absent de `content.md`).
4. Horaires d'ouverture.
5. Témoignage client (verbatim requis).

## (c) Écarts vs DESIGN.md
- Aucun écart de palette : `#FF5733` (primary), `#19100C` (night), `#50382A` (warm), `#F4F4F4` (cream) — tous de `palette_for_design`.
- `secondary` (null) → dérivé des ombres du primary (`#C23F1E`, `#A63315`), déclaré.
- Section « preuve chiffrée » omise (aucune donnée d'avis/chiffre extractible) → remplacée par le positionnement Trophée (reformulation, zéro chiffre).

## (d) Copy retravaillée (original → réécrit → formule)
- « Nous offrons du haut de gamme » → « Le haut de gamme assumé — un service soigné et une salle raffinée » → bénéfice-serveur.
- « Des repas exceptionnels » → « Des repas exceptionnels, servis sans effort. » → heading + bénéfice.
- « Nos vins de qualité » → « Une carte des vins choisie pour accompagner la fusion orientale & française » → obtenir accord.
- « Les spécialités du Chef » → reformulées en bénéfices (3 cartes) → obtenir choix.
- Headline hero → « Cuisine orientale & française, dans une salle·sentinelle du haut de gamme. » → formule `{métier} à {ville} qui {différenciateur}` (fusion + haut de gamme, tous du réel extrait).
- CTA faibles « RÉSERVATION / CONTACTEZ-NOUS / Réserver une table » → « Réserver une table », « Votre table vous attend. », « Appeler : 01 45 08 02 03 » → `[verbe] + [ce qu'on obtient]`.

## Self-check
- grep `lorem`, `unsplash`, `placeholder.com`, `picsum` → aucun.
- Aucun chiffre inventé (aucun nb d'avis, aucune année, aucun prix).
- AI-tells reformulés : « expérimentez », « chef-d'œuvre » (issu de l'extraction réelle), pas de « At its core »/« significantly ». Pas de point d'exclamation marketing.
- Images : uniquement `asset-pack/images/` `kept`.

## Sortie dashboard
- Copie : `ia_echanges/Restaurant Paris (auto)/PROMPT/5/index.html` + `PROMPT/5/assets/{hero-chouchou.jpg,table.jpg}` + `capture.png`.