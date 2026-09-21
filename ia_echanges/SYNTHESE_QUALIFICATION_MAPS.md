# Synthèse qualification — campagne « 🗺️ Restauration — Maps » (id 38)

Décisions issues des 68 listes sources de la campagne (51, 53-60, 68-75, 78-83, 97-101, 104-123, 133, 136-138), soit **2 542 prospects**.
Axes de lecture : `Score` = obsolescence du site (0 moderne → 100 cassé/daté) ; `Opp` = opportunité commerciale ; `Reco` = décision.
Méthodologie : fetch réel des sites (HTTP + scoring obsolescence + signaux), reclassement des doublons couverts (domaines déjà qualifiés dans d'autres listes de la campagne 39 → verdict source copié), réseaux/plateformes identifiés sans fetch.

---

## Répartition finale (source de vérité = `data/prospection.db`, `json_extract(data_extra,'$.ia_reco')`)

| Liste décision | id | Prospects |
|---|---|---|
| ✅ À contacter | 143 | **561** |
| ⚠️ À vérifier | 144 | **1 229** |
| 🛑 À écarter | 145 | **4** |
| ⏸️ Site moderne (sains) | 146 | **748** |
| **Total** | | **2 542** |

---

## 1. ✅ À CONTACTER — 561 prospects (action immédiate)

Passage direct en séquence d'envoi (email ou téléphone si pas d'email).

- **404 sans site web, téléphone présent (Opp=5)** → candidats à la création de site : gestion par téléphone. ~88 % des contacts disposent d'un téléphone (536/561).
- **Sites datés (Opp=3, score ≥ 40)** : 91 établissements au site techniquement obsolète → offre refonte.
- **Sites cassés (Opp=4, score=100)** : 41 sites définitivement HS (DNS/500/503/SSL) → offre refonte prioritaire.
- **Opport/cliniques/santé (Opp 50-75)** : cabinets esthétiques et cliniques avec score fort de difficulté d'obsolescence → prioritaires.

> Email présent sur 93 prospects (17 %) ; le reste passe par téléphone (536) ou formulaire du site.

---

## 2. ⚠️ À VÉRIFIER — 1 229 prospects (tri humain)

### 2a. Masse à zapper (~537) — réseaux / groupes / grands comptes (Opp=35)
Concessions multifranchises (VGRF Paris, Central Autos), réseaux de courtage (CAFPI, Crédit Expert, Avisofi, Credixia, Immofinances, SOFIAP, groupe Faubourg, groupe ICS, my-finance), réseaux immobiliers (laforêt, manda, nestenn, John Taylor, data-immo, homeloop, Daniel Féau), promoteurs (Bouygues Immobilier, BNP RE, UrbaXim, Marignan, SLCI, Dubois, lnc, Accueil Immobilier), institutions (CHU, MAIF, Malakoff Humanis, Sogecap, Afme), écoles/grandes formations (CCI, CER), portails d'annonces (logic-immo, seloger).

### 2b. Plateformes / pas de site propre (Opp=2) — ~634
CyberPret, credirama, doly.me, plusse.co + entreprises sans site ET sans téléphone (impossibles à joindre).

### 2c. Doute technique seulement (~58)
Sites réels mais non analysables (403 anti-bot, certificat TLS invalide, 308 redirect loop, timeout, score élevé avec doute) — meilleurs candidats à re-regarder.

> Email présent sur 365 prospects (30 %). La grande majorité (réseaux/plateformes) est à écarter du ciblage.

---

## 3. 🛑 À ÉCARTER — 4 prospects (zapper définitivement)

| id | Nom | Raison |
|---|---|---|
| 6019 | chirurgie-dermatologique-paris.com | Doublon / hors cible (médecin Paris) |
| 6042 | senior.skarlett.fr | Doublon de skarlett.fr (site vitrine) |
| 6046 | immog2c.fr | Site vitrine réseau, société sur immog2c.com |
| 6093 | remeur (homeland.immo) | Chargeur réseau homeland — grand compte |

`ecarte=1` posé → exclus de l'auto-send.

---

## 4. ⏸️ SITE MODERNE / SAINS — 748 prospects (en attente)

Sites à jour (score ≤ 15) : pas de projet refonte immédiat évident. À re-sonder plus tard (pas de contact immédiat).

---

## Actions réalisées

1. **Qualification `liste_51`** (1 052 leads orphelins) : fetch des 375 sites propres (16 lots parallèles + retests), 21 réseaux/plateformes identifiés sans fetch, verdicts couverts copiés depuis les listes sources de la campagne 39, 89 sans site reclassés, 2 emails placeholder nettoyés. Scan API : `ok=true, ecarts=0`.
2. **Reclassement global campagne 38** : 68 listes sources **vidées**, 2 542 prospects déplacés dans les 4 listes décision (id 143-146) le 2026-09-16. `prospect_events` journalisés (`reclassement`). Backup avant déplacement : `backups/prospection_pre_reclassement_20260916_162735.db`.
3. Listes sources vidées confirmées : 0 prospect restant dans les 68 listes.