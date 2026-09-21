# PROMPT — Structurer la Prospection Machine en SaaS complet

Rôle : développeur senior chargé de restructurer un outil de prospection existant (scraping/qualification déjà fonctionnels, envoi SMTP déjà intégré) en un système complet, piloté par une machine à états, qui automatise tout le cycle de vie d'un prospect jusqu'à fermeture, désinscription ou RDV obtenu.

## Contexte déjà arbitré (ne pas remettre en cause)

- Deux domaines d'envoi séparés : un pour particuliers (`marcdev.com`), un pour agences (`jeanmarcdev.com`).
- Plusieurs boîtes mail par domaine (Zoho Mail, 2-3 boîtes particuliers, 2 boîtes agences), rotation d'envoi entre elles.
- Premier email sans lien ni pièce jointe.
- Séquences distinctes déjà rédigées pour particuliers et agences.
- Pas de tracking d'ouverture fiable disponible — le taux de réponse est la métrique de référence, pas le taux d'ouverture.
- Ces deux domaines sont construits sur le vrai nom de l'utilisateur (pas des domaines jetables) — la réputation compte sur le long terme, pas seulement pour cette campagne.
- Une seule mécanique d'envoi/relance/suivi pour TOUTES les campagnes, quelle que soit leur source de leads — pas un moteur différent par type de campagne.
- Sources de leads multiples et hétérogènes : scraping (Google Maps/Ads), import CSV, import JSON, listes construites manuellement avec l'aide de l'IA. D'autres s'ajouteront.
- Reste sur de l'envoi gratuit (boîtes mail perso/Zoho) pour l'instant — pas de service payant pour le moment, à réévaluer plus tard sans reconstruire le moteur.

## 0. Audit avant de commencer (obligatoire, à faire en premier)

Une partie de ce qui suit existe peut-être déjà dans l'outil actuel (scraping, qualification, envoi SMTP fonctionnels). **Avant d'écrire la moindre ligne de code**, l'agent doit :

1. Lister les modules/fonctions déjà en place et ce qu'ils font réellement (pas ce que le nom du fichier suggère).
2. Identifier lesquels correspondent déjà à une pièce du système décrit ci-dessous (modèle de données, machine à états, moteur d'envoi, détection de réponse, etc.) et peuvent être adaptés plutôt que réécrits.
3. Signaler explicitement les endroits où la logique actuelle est codée en dur pour un seul cas (ex. "particulier vs agence", un seul format d'import) et qui devra être généralisée selon la section 8.
4. Ne proposer une réécriture complète d'un module que si l'adapter coûterait plus cher que le refaire — sinon, étendre l'existant.

## 1. Modèle de données minimal

- **Prospect** : identité (nom, email, source, cible = particulier/agence), statut courant, historique de qualification, campagne rattachée.
- **Campagne/Séquence** : liste ordonnée d'étapes (email initial + N relances), délais entre étapes, condition d'arrêt.
- **Boîte d'envoi** : domaine, adresse, quota jour, compteur d'envoi du jour, dernier envoi.
- **Message/Événement** : chaque email envoyé ou reçu, avec `Message-ID`, `In-Reply-To`, timestamp, boîte utilisée, type (envoi initial, relance, réponse entrante, NDR/bounce).

### Couche d'ingestion (un adaptateur par source, un seul schéma en sortie)

Toutes les sources de leads (scraping, CSV, JSON, liste générée par l'IA, et toute source future) passent par un adaptateur dédié dont le seul rôle est de mapper le format brut vers le schéma `Prospect` ci-dessus. Aucune logique de qualification, de séquençage ou d'envoi ne doit vivre dans un adaptateur — son unique responsabilité est la conversion de format.

- **CSV/JSON** : mapping direct des colonnes/clés vers les champs `Prospect`.
- **Liste générée par l'IA** : au lieu de convertir une sortie texte libre à la main, demander à l'agent de faire produire directement du JSON conforme au schéma `Prospect` à cette étape — élimine une conversion manuelle répétée.
- **Scraping** : adapter l'existant (cf. section 0) pour qu'il produise le même schéma en sortie plutôt que son propre format.

Une fois passé par son adaptateur, un prospect est indiscernable des autres pour tout le reste du système (qualification, séquençage, envoi, machine à états, dashboard) — seul le champ `source` conserve la trace d'origine, à des fins de reporting uniquement.

## 2. Machine à états du prospect

Statuts et transitions à implémenter explicitement (pas de logique implicite éparpillée dans le code d'envoi) :

```
qualifié → en_séquence → [relance_1] → [relance_2] → [relance_N] → sans_réponse (fermé)
en_séquence → (réponse détectée) → à_traiter_humain → {rdv_obtenu | pas_intéressé | à_relancer_plus_tard}
en_séquence → (désinscription détectée) → ne_plus_contacter (définitif, toutes campagnes futures)
en_séquence → (bounce dur détecté) → adresse_invalide (fermé, retiré de la base)
```

Toute réponse entrante, quelle qu'elle soit, doit **suspendre immédiatement** les relances automatiques sur ce prospect — jamais de relance envoyée après une réponse, même si la classification du contenu prend du temps.

## 3. Moteur d'envoi

- Respecte le quota jour par boîte (défini en amont), rotation round-robin entre les boîtes disponibles du domaine correspondant à la cible (particulier/agence).
- Espace les envois dans la journée (pas un burst de 30 emails à 8h01) — répartir sur plusieurs heures pour ressembler à un envoi humain.
- Vérifie le quota restant avant chaque envoi programmé ; si le quota du jour est atteint sur toutes les boîtes d'un domaine, reporte au lendemain plutôt que dépasser.
- **Découpler l'envoi derrière une interface** (ex. `envoyer(message, boîte)`), même si la seule implémentation aujourd'hui est du SMTP perso gratuit. Le jour où le volume justifie un service payant, on change une implémentation derrière l'interface, pas toute la mécanique de séquençage/relance construite autour.

## 4. Détection des réponses (le cœur du système)

- Polling IMAP périodique (toutes les 5-15 min suffisent, pas besoin de temps réel) sur chaque boîte d'envoi.
- Matching de thread via l'en-tête `In-Reply-To`/`References` pointant vers le `Message-ID` du mail envoyé — pas du matching par sujet ou par expéditeur seul, trop fragile.
- **Distinguer explicitement 3 types de retour** avant de les traiter comme une "réponse" :
  1. Réponse humaine réelle → passe en `à_traiter_humain`.
  2. Réponse automatique (absence du bureau, auto-reply) → détectable via en-têtes standards (`Auto-Submitted`, `X-Autoreply`) ou mots-clés — ne pas compter comme une vraie réponse, ne pas non plus relancer entre-temps ; reprendre la séquence normalement après la date de retour si elle est mentionnée.
  3. Bounce/NDR (non-delivery report) → à traiter comme substitut de métrique de bounce rate, puisqu'il n'y a pas d'ESP avec webhook dédié. Compter ces NDR par domaine/jour pour le garde-fou de la section 6.
- Détection de désinscription : mots-clés explicites ("désinscription", "stop", "ne plus me contacter") → statut `ne_plus_contacter` définitif, exclusion de toute campagne future même sur un autre domaine ou une autre cible. Ce n'est pas seulement une question légale : ces domaines portent le vrai nom de l'utilisateur, recontacter quelqu'un après un refus explicite abîme une réputation qu'il devra porter au-delà de cette seule campagne.

## 5. Relances automatiques

- Particuliers : jusqu'à 3 touches (email initial + 2 relances), cadence à espacer par l'agent selon la séquence déjà rédigée.
- Agences : jusqu'à 2 touches (email initial + 1 relance à J+4/5, déjà validée).
- Une relance ne part que si : pas de réponse détectée, pas de bounce détecté, quota du jour disponible sur une boîte du bon domaine, et nombre max de touches non atteint.
- Après la dernière touche sans réponse → statut `sans_réponse`, dossier fermé automatiquement, pas d'action humaine requise.

## 6. Garde-fou de délivrabilité (circuit breaker)

- Suivre par domaine et par jour : nombre de NDR/bounces reçus, nombre de désinscriptions.
- Si le taux de bounce dépasse un seuil (ex. 5% des envois du jour) ou si plusieurs désinscriptions arrivent en rafale sur un domaine → **pause automatique des envois sur ce domaine** et alerte, plutôt que de laisser la machine continuer à dégrader une réputation déjà entamée pendant que personne ne regarde.

## 7. Tableau de bord

- Vue "historique" par prospect : tous les messages du thread (envoyés + reçus), statut courant, prochaine action prévue.
- Vue "campagne" : nombre envoyé, nombre en attente de relance, **taux de réponse** (métrique principale), nombre de RDV obtenus, nombre de désinscriptions, nombre de bounces — par domaine et cumulé.
- Pas de métrique de taux d'ouverture affichée nulle part dans le dashboard — son absence de fiabilité doit être assumée plutôt que remplacée par une fausse estimation.

## 8. Rendre la machine générique pour toute prospection future

Cet outil ne servira pas qu'à la refonte de site pour particuliers et à la sous-traitance agences — il y a déjà d'autres campagnes en parallèle (immobilier, courtiers, concessions auto, cliniques esthétiques, écoles de formation) et il y en aura d'autres après. Ne fige rien de spécifique à "particulier vs agence" dans le code : ce sont des données de configuration, pas des cas particuliers en dur.

- **Remplacer le champ "cible = particulier/agence" par un modèle générique `Offre` + `Segment`.** Une nouvelle campagne (nouveau secteur, nouveau produit) = une nouvelle entrée de configuration (nom, domaine associé, séquence associée, règles de qualification), jamais une branche de code supplémentaire. Le test : ajouter une 3ᵉ cible ne doit toucher aucun fichier de logique métier, seulement des données.
- **Templates de séquence avec variables de fusion** (`{{prenom}}`, `{{entreprise}}`, `{{secteur}}`, `{{offre}}`) plutôt que du texte codé en dur par campagne — un nouveau secteur ne nécessite qu'un nouveau template, pas une nouvelle fonction d'envoi.
- **Règles de qualification configurables par campagne** (mots-clés, scoring, critères d'exclusion) plutôt qu'une fonction de qualification écrite pour un seul cas. Le mécanisme qui élimine "une bonne masse" de leads doit être un moteur de règles réutilisable, pas une logique spécifique aux particuliers.
- **Pool de domaines/boîtes générique**, taggé par campagne plutôt que codé en dur ("domaine agences", "domaine particuliers"). Ajouter un 3ᵉ domaine pour un nouveau secteur = une entrée dans le pool, avec sa propre courbe de warmup et ses propres quotas — réutilise le même moteur de rotation et le même circuit breaker de la section 6, qui doit donc être écrit une fois pour être appliqué à n'importe quel domaine ajouté plus tard, pas seulement les deux actuels.
- **Liste de suppression centrale unique**, indépendante de toute campagne — une désinscription reste valable sur tous les domaines et tous les secteurs, présents et futurs. C'est un registre transversal, pas une table par campagne.
- **File d'attente humaine unifiée** (`à_traiter_humain`) qui agrège tous les prospects à traiter, toutes campagnes confondues, dans une seule vue — pour ne pas se retrouver à checker N dashboards séparés quand plusieurs campagnes tournent en même temps.
- **Prévoir le canal comme une dimension, pas une hypothèse figée sur l'email.** Il y a déjà eu une campagne WhatsApp (Pack Présence) séparée du système email. Si l'architecture le permet sans effort disproportionné, modélise une "touche" comme générique (email OU WhatsApp OU autre) rattachée au même prospect et à la même machine à états, plutôt que de dupliquer toute la mécanique pour chaque nouveau canal futur. Si c'est trop de travail maintenant, au minimum ne pas coder de suppositions "c'est forcément un email" en dur dans le cœur du moteur d'états.
- **Tableau de bord multi-campagnes** : les métriques de la section 7 (taux de réponse, RDV, désinscriptions, bounces) doivent être filtrables par campagne/secteur/domaine ET consultables en vue agrégée, pour comparer la performance entre plusieurs prospections menées en parallèle sans devoir ouvrir un outil différent pour chacune.

## 9. Ce qui n'est pas à faire

- Ne pas construire de tracking d'ouverture par pixel — inutile vu le contexte (section déjà tranchée), et ça ajoute un lien/image dans le premier email qu'on cherche justement à éviter.
- Ne pas mélanger les statuts par domaine — un prospect `agence` ne doit jamais recevoir un email du domaine `particuliers` même en cas de bug de routage ; valider ce garde-fou par un test explicite.
