# Mapping des colonnes APIFY `crawler-google-places` → sortie

L'export APIFY contient ~200-250 colonnes (notation `parent/index/champ`). Le script lit **par nom**,
donc seules ces colonnes comptent ; le reste est ignoré. Encodage **UTF-8 avec BOM**, séparateur `,`,
guillemets RFC 4180.

## Colonnes de sortie (`prospects.csv`) et leur source

Ordre exact : `Prospecter ?, Opportunité, Score, Nom, Nom normalisé, Ville, Catégorie, Site Web, Email, Instagram, LinkedIn, Téléphone, Signaux, URL Google Maps`

| Sortie | Colonne(s) APIFY / origine | Remarques |
|---|---|---|
| Prospecter ? | (vide) | case cochée par l'utilisateur (O/N) — décision manuelle |
| Opportunité | calculé (`analyze_site`) | `Aucun site` / `Site cassé` / `Site daté (N)` / `Site à vérifier (N)` / `Site moderne (N)` / `Non vérifié` |
| Score | calculé (`analyze_site`) | obsolescence 0-100 ; vide pour `Aucun site` / `Site cassé` / `Non vérifié` |
| Nom | `title` | nom source brut, toujours rempli |
| Nom normalisé | IA (post-traitement, sous-agent Haiku) | cœur distinctif (nom usuel), casse d'origine ; `domain`/`website` sert d'indice ; vide si non exécuté |
| Ville | `city` | |
| Catégorie | `categoryName` | catégorie principale affichée |
| (matching catégorie) | `categoryName` + `categories/0` … `categories/8` | jusqu'à 9 catégories secondaires, souvent en français |
| Site Web | `website` | vide ≈ 1 lead sur 9 → `Aucun site` |
| Email | `emails/0`, `emails/1`, `emails/2`, `emails/3` | **une ligne de sortie par email rempli** |
| Instagram | `instagrams/0` | un seul index exposé (le 1er) |
| LinkedIn | `linkedIns/0` | un seul index exposé |
| Téléphone | `phone` | format avec espaces (ex. `+33 6 12 34 56 78`) |
| Signaux | calculé (`analyze_site`) | détail des signaux d'obsolescence (le *pourquoi*) |
| URL Google Maps | `url` | lien `google.com/maps/search/?api=1&query=…&query_place_id=…` |

## Colonnes de contact disponibles mais non retenues par défaut

APIFY expose aussi : `facebooks/0`, `pinterests/0`, `tiktoks/0`, `twitters/0`,
`phoneUnformatted`, `phones/0..1`, `phonesUncertain/0..16` (OCR bas niveau, peu fiable),
`domain` (domaine seul). À ajouter au besoin si la cible de prospection l'exige.

## Taux de remplissage observés (échantillon Cannes, 28 leads)

| Champ | Remplissage |
|---|---|
| `title`, `address`, `categoryName` | 100 % |
| `phone` | ~96 % |
| `website` | ~89 % |
| `instagrams/0` | ~53 % |
| au moins un `emails/*` | ~46 % |
| `linkedIns/0` | ~25 % |

→ Le filtre « joignable » s'appuie surtout sur **téléphone + Instagram** ; l'email seul exclurait trop de leads.
