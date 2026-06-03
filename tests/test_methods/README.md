# Test Lighthouse Batch

Test de résistance pour valider si Lighthouse CLI peut remplacer l'auditeur actuel (PageSpeed API) pour des campagnes de 200 audits.

## Résultats des tests (10 Mai 2026)

### Résumé

| Métrique | Valeur |
|----------|--------|
| Taux succès | **70-80%** |
| Temps moyen / URL | **50s** (simulate mode) |
| Projection 200 URLs | **~2h45** |
| Projection 200 URLs (provided) | **~1h** |
| Crash / plantage | **Aucun** — 0 crash mémoire |
| Erreurs SSL / certificat | Catchées proprement |
| Timeouts (>180s) | Catchés proprement |

### Découverte critique : rate limit PageSpeed API

**PageSpeed API rate-limité à 429 après ~10 requêtes séquentielles sans délai.**

L'auditeur actuel contourne ça avec `time.sleep(3)` entre chaque appel, ce qui le ralentit à ~15s/URL. À ce rythme, 200 URLs = ~50min, mais avec le risque de rate-limit en milieu de batch.

**Lighthouse CLI n'a AUCUNE limite de débit.** Zéro. C'est son avantage décisif.

### Comparaison Lighthouse vs PageSpeed API

| Critère | Lighthouse CLI | PageSpeed API (actuel) |
|---------|---------------|----------------------|
| Stabilité | 70-80% succès | ~90%+ (quand pas rate-limité) |
| Temps/URL | 50s (simulate) / 20s (provided) | 5-15s (selon délai) |
| Rate limit | **Aucun** | **429 après ~10 req** |
| Coût | Gratuit (Chrome local) | Gratuit (quota limité) |
| Précision | Même moteur Lighthouse | Même moteur Lighthouse |
| Données CrUX | ❌ non (pas de terrain) | ✅ Oui (si dispo) |
| Contextualisation | Mobile/Desktop | Mobile/Desktop |
| Dépendances | Node.js + Chrome | API key Google |
| Risque mémoire | Moyen (Chrome ~300MB) | Aucun (API HTTP) |

### Projection pour 200 URLs

**Scénario A — simulate (rapide mais réaliste)**
- 200 × 50s = 10 000s = **2h47**
- RAM: ~300-500MB crête
- Taux succès estimé: 75%

**Scénario B — provided (brut, sans throttling)**
- 200 × 20s = 4 000s = **1h07**
- Même précision sur les métriques brutes (LCP, FCP, etc.)
- Le score performance sera surévalué (pas de throttling)

**Scénario C — devtools (très réaliste)**
- 200 × 90s = 18 000s = **5h00**
- Trop lent pour un batch de production

### Verdict

> **✅ Lighthouse CLI est viable pour remplacer l'auditeur actuel.**
>
> Avantage décisif : pas de rate limit, pas de quota API.
> Inconvénient : ~3h pour 200 URLs (vs ~50min pour PageSpeed avec délais).

**Recommandation :** utiliser `--throttling-method=simulate` pour les audits de production.
C'est le meilleur compromis entre vitesse et réalisme.

### Optimisations possibles

1. **Pipeline parallèle** — 2 workers Lighthouse (risque RAM, mais divise le temps par 2)
2. **Cache Chrome** — Réutiliser un profile Chrome persistent (`--chrome-flags=--user-data-dir=...`)
3. **Throttling provided** — Pour les métriques brutes, appliquer notre propre formule de score
4. **Timeout adaptatif** — 60s pour les petits sites, 180s pour les gros

## Usage

```bash
# Test rapide (10 URLs PME)
python tests/test_methods/test_lighthouse_batch.py --quick

# 200 leads depuis SQLite
python tests/test_methods/test_lighthouse_batch.py --from-db --limit 200

# Même test + comparaison PageSpeed API
python tests/test_methods/test_lighthouse_batch.py --from-db --limit 20 --compare

# Depuis fichier
python tests/test_methods/test_lighthouse_batch.py --from-file urls.txt

# Export JSON
python tests/test_methods/test_lighthouse_batch.py --from-db --limit 50 --output resultats.json

# Desktop
python tests/test_methods/test_lighthouse_batch.py --quick --strategy desktop

# Throttling réel (lent mais réaliste)
python tests/test_methods/test_lighthouse_batch.py --quick --real-throttle
```

## Prérequis

- Node.js v22+
- Lighthouse CLI global: `npm install -g lighthouse` (déjà fait)
- Chrome (déjà dispo `C:\Program Files\Google\Chrome\Application\`)
