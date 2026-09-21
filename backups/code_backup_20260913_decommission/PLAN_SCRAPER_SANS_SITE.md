# Plan : Scraper Google Maps optimisé pour leads sans site web

## Contexte

La personne qui reprend l'application ne gérera QUE les leads sans site web. Le scraper doit :
- Collecter des leads AVEC au moins un téléphone OU email (pas de leads orphelins)
- Fonctionner en France ET au Bénin
- Rotation intelligente de villes et variantes de mots-clés via LLM
- Arrêt automatique si plus de résultats (pas de boucle infinie)
- Fiabilité des données (l'utilisateur ne vérifiera rien avant de contacter)

---

## Étape 1 : Database — Migration `pays`

### Objectif
Ajouter un champ `pays` (TEXT, défaut 'fr') aux tables `leads_bruts` et `campagnes` pour tracker le pays d'origine de chaque lead.

### Fichier : `database/schema.py`

**Dans la fonction `migrate_db()`** (vers la ligne 240, après les autres migrations), ajouter :

```python
# ─── Migration: pays pour leads_bruts et campagnes ───
try:
    conn.execute("SELECT pays FROM leads_bruts LIMIT 1")
except:
    conn.execute("ALTER TABLE leads_bruts ADD COLUMN pays TEXT DEFAULT 'fr'")
    logger.info("[MIGRATE] Added pays column to leads_bruts")

try:
    conn.execute("SELECT pays FROM campagnes LIMIT 1")
except:
    conn.execute("ALTER TABLE campagnes ADD COLUMN pays TEXT DEFAULT 'fr'")
    logger.info("[MIGRATE] Added pays column to campagnes")
```

### Vérification
Lancer le serveur Flask, vérifier que la migration passe sans erreur. Vérifier en DB :
```sql
PRAGMA table_info(leads_bruts);  -- doit montrer la colonne pays
PRAGMA table_info(campagnes);    -- doit montrer la colonne pays
```

---

## Étape 2 : CityRotator — Villes béninoises

### Objectif
Permettre la rotation de villes pour le Bénin (20 villes, du plus peuplé au moins peuplé).

### Fichier : `core/city_rotator.py`

**Dans le dict `_CITIES`** (vers la ligne 28), ajouter la clé `"bj"` après `"lu"` :

```python
"bj": [
    "Cotonou", "Porto-Novo", "Parakou", "Djougou", "Bohicon",
    "Abomey", "Natitingou", "Lokossa", "Comè", "Ouidah",
    "Sèmè-Kpodji", "Abomey-Calavi", "Allada", "Kétou", "Pobè",
    "Sakété", "Dassa-Zoumè", "Savalou", "Bassila", "Glo-Djigbé",
],
```

### Vérification
Test unitaire rapide :
```python
from core.city_rotator import CityRotator
r = CityRotator(country="bj")
assert r.has_more()
batch = r.next_batch("hôtel", batch_size=3)
assert len(batch) == 3
assert "Cotonou" in batch[0]
```

---

## Étape 3 : Scraper — Module variantes de mots-clés LLM

### Objectif
Créer un module qui utilise Groq (LLaMA 3.3 70B) pour générer des variantes de mots-clés, permettant de trouver des leads que la requête originale ne couvre pas.

### Fichier : `scraper/keyword_variants.py` (NOUVEAU)

Créer ce fichier avec le contenu suivant :

```python
# -*- coding: utf-8 -*-
"""
scraper/keyword_variants.py
Génère des variantes de mots-clés via LLM pour élargir la recherche Google Maps.
"""
import json
import logging
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

logger = logging.getLogger(__name__)


def generate_keyword_variants(keyword: str, city: str, country: str = 'fr',
                               max_variants: int = 8) -> list[str]:
    """
    Génère des variantes de mots-clés pour élargir la recherche Google Maps.

    Ex: "hôtel Cotonou" → ["hôtel boutique Cotonou", "bnb Cotonou",
        "auberge Cotonou", "guest house Cotonou", ...]

    Args:
        keyword:     Mot-clé de base (ex: "hôtel")
        city:        Ville ciblée (ex: "Cotonou")
        country:     Code pays (fr, bj, be, ...)
        max_variants: Nombre max de variantes à retourner

    Returns:
        Liste de variantes de mots-clés (ex: ["hôtel boutique", "bnb", ...])
        Retourne [keyword] en cas d'erreur.
    """
    try:
        from config_manager import handle_llm_call

        country_name = {
            "fr": "française", "bj": "béninoise", "be": "belge",
            "ch": "suisse", "lu": "luxembourgeoise",
        }.get(country, "française")

        prompt = f"""Tu es un expert en recherche Google Maps pour la prospection B2B.

Génère {max_variants} variantes du mot-clé "{keyword}" pour la ville "{city}" (contexte {country_name}).

Règles :
- Inclure des synonymes et termes proches
- Adapter au contexte local ({country_name})
- Inclure des termes anglais si couramment utilisés (ex: "guest house", "boutique hotel")
- Retourner UNIQUEMENT un tableau JSON valide, sans markdown ni explication
- Format : ["variante1", "variante2", ...]
- NE PAS inclure la ville dans les variantes (sera ajoutée automatiquement)

Exemples pour "hôtel" :
["hôtel", "hôtel boutique", "bnb", "auberge", "guest house", "maison d'hôtes", "résidence", "lodging"]

Mot-clé : {keyword}
Ville : {city}"""

        print(f"   [KeywordVariants] Génération de variantes pour '{keyword}' à {city}...")
        raw = handle_llm_call(
            prompt=prompt,
            system="Tu es un assistant de prospection. Réponds UNIQUEMENT avec du JSON valide, sans markdown ni explication.",
            model="llama-3.3-70b-versatile"
        )

        # Nettoyage de la réponse
        cleaned = raw.strip()
        if "```" in cleaned:
            import re
            match = re.search(r'```(?:json)?\s*([\s\S]*?)```', cleaned)
            if match:
                cleaned = match.group(1).strip()

        variants = json.loads(cleaned)

        if not isinstance(variants, list) or not variants:
            raise ValueError(f"Réponse invalide : {raw[:200]}")

        # Filtrer et dédupliquer
        seen = set()
        result = []
        for v in variants:
            v_str = str(v).strip()
            if v_str and v_str.lower() not in seen and v_str.lower() != keyword.lower():
                seen.add(v_str.lower())
                result.append(v_str)

        # Toujours inclure le mot-clé original en premier
        final = [keyword] + result[:max_variants]
        print(f"   [KeywordVariants] {len(final)} variantes générées")
        return final

    except ImportError:
        logger.warning("config_manager non disponible — variantes LLM désactivées")
        return [keyword]
    except Exception as e:
        logger.error(f"[KeywordVariants] Erreur : {e}")
        print(f"   [KeywordVariants] ⚠️ Erreur : {e} — Utilisation du mot-clé original")
        return [keyword]


if __name__ == "__main__":
    keyword = sys.argv[1] if len(sys.argv) > 1 else "hôtel"
    city = sys.argv[2] if len(sys.argv) > 2 else "Cotonou"
    country = sys.argv[3] if len(sys.argv) > 3 else "bj"
    variants = generate_keyword_variants(keyword, city, country)
    print(f"\nVariantes pour '{keyword}' à {city} :")
    for i, v in enumerate(variants, 1):
        print(f"  {i}. {v}")
```

### Vérification
```bash
python scraper/keyword_variants.py "hôtel" "Cotonou" "bj"
```
Doit retourner 6-8 variantes comme ["hôtel", "bnb", "auberge", "guest house", ...]

---

## Étape 4 : Scraper main.py — Modifications complètes

### Objectif
Adapter le scraper pour supporter le pays, le filtre contact, les variantes LLM, et les limites de sécurité.

### Fichier : `scraper/main.py`

### 4a. Nouveaux imports (en haut du fichier, après les imports existants)

Ajouter après `import psutil` (ligne 17) :

```python
import re
```

### 4b. Regex téléphone bénin (après la fonction `_email_confidence`, vers la ligne 77)

Ajouter les constantes et modifier `search_phone_on_website` :

```python
# ─── Regex téléphones ────────────────────────────────────────────────
_PHONE_FR = r'(?:(?:\+|00)33[\s.-]{0,3}(?:\(0\)[\s.-]{0,3})?|0)[1-9](?:(?:[\s.-]?\d{2}){4}|\d{2}(?:[\s.-]?\d{3}){2})'
_PHONE_BJ = r'(?:\+229[\s.-]?)?(?:21|22|23|24|25|26|27|28|29|30|31|32|33|34|35|36|37|38|39|40|41|42|43|44|45|46|47|48|49|50|51|52|53|54|55|56|57|58|59|60|61|62|63|64|65|66|67|68|69|70|71|72|73|74|75|76|77|78|79|80|81|82|83|84|85|86|87|88|89|90|91|92|93|94|95|96|97|98|99)\d{4}'
```

Remplacer la fonction `search_phone_on_website` (lignes 87-104) par :

```python
def search_phone_on_website(url, country='fr'):
    """Cherche un numero de telephone sur une page web s'il est manquant sur Google Maps."""
    if not url:
        return None
    try:
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        pattern = _PHONE_BJ if country == 'bj' else _PHONE_FR
        tels_trouves = re.findall(pattern, response.text)
        if tels_trouves:
            return tels_trouves[0].strip()
        return None
    except Exception as e:
        logger.error(f"Erreur recherche telephone sur {url}: {e}")
        return None
```

### 4c. Arguments CLI (dans `main_async`, vers la ligne 460)

Remplacer le bloc argparse par :

```python
    parser = argparse.ArgumentParser(description="Scraper Google Maps via Playwright")
    parser.add_argument("--keyword", required=True, help="Le metier (ex: 'restaurant')")
    parser.add_argument("--city", required=True, help="La ville (ex: 'Cotonou')")
    parser.add_argument("--limit", type=int, default=20, help="Nombre max de resultats (defaut: 20)")
    parser.add_argument("--min-emails", type=int, default=None, help="Nombre minimum de leads avec email requis")
    parser.add_argument("--campaign-id", type=int, default=None, help="ID de la campagne rattachée")
    parser.add_argument("--multi-zone", action="store_true", help="Utiliser l'agent de zones LLM")
    parser.add_argument("--offset", type=int, default=0, help="Nombre de résultats à ignorer")
    parser.add_argument("--min-reviews", type=int, default=0, help="Nombre minimum d'avis requis")
    parser.add_argument("--secteur", type=str, default="", help="Étiquette secteur (ex: immobilier)")
    parser.add_argument("--country", type=str, default="fr", help="Code pays (fr, bj, be, ch, lu)")
    parser.add_argument("--require-contact", action="store_true",
                        help="Ne garder que les leads avec téléphone OU email")
    parser.add_argument("--max-passes", type=int, default=30,
                        help="Nombre maximum de passes de zones (défaut: 30)")
    parser.add_argument("--keyword-variants", action="store_true",
                        help="Générer des variantes de mots-clés via LLM")
```

### 4d. Locale adaptée (dans `scrape_google_maps`, vers la ligne 172)

Remplacer :
```python
        ctx = await browser.new_context(
            locale="fr-FR",
```

Par :
```python
        locale = "fr-BJ" if (kwargs.get('country') == 'bj') else "fr-FR"
        ctx = await browser.new_context(
            locale=locale,
```

Et ajouter `country='fr'` comme paramètre de `scrape_google_maps` :

```python
async def scrape_google_maps(keyword, city, limit=20, known_names=None, country='fr'):
```

Puis dans la boucle principale (ligne 592), passer le pays :
```python
batch_places = await scrape_google_maps(args.keyword, zone, limit_zone,
                                         known_names=seen_noms_global,
                                         country=args.country)
```

### 4e. Blacklist domaines étendue (dans `_enrichir_place`, vers la ligne 536)

Remplacer :
```python
            blacklist = ["google.com", "facebook.com", "instagram.com",
                         "tripadvisor", "yellowpages", "yandex.com", "yahoo.com"]
```

Par :
```python
            blacklist = [
                # Réseaux sociaux
                "google.com", "facebook.com", "instagram.com", "twitter.com",
                "linkedin.com", "tiktok.com", "youtube.com",
                # Annuaires FR
                "pagesjaunes.fr", "societe.com", "infogreffe.fr", "pappers.fr",
                "verif.com", "manageo.fr", "annuaire-entreprises.data.gouv.fr",
                "tripadvisor", "yellowpages", "yandex.com", "yahoo.com",
            ]
```

Et ajouter `pays` dans le dict retour de `_enrichir_place` :

```python
        return {
            ...
            'campaign_id':  args.campaign_id,
            'pays':         args.country,  # ← AJOUTER
        }
```

### 4f. Variantes de mots-clés (dans `main_async`, après le chargement de `seen_noms_global`, vers la ligne 508)

Ajouter le bloc de génération de variantes :

```python
    # ── Variantes de mots-clés via LLM ──────────────────────────────
    keyword_list = [args.keyword]
    if args.keyword_variants:
        try:
            from scraper.keyword_variants import generate_keyword_variants
            keyword_list = generate_keyword_variants(args.keyword, args.city, args.country)
            print(f"   [VARIANTS] {len(keyword_list)} mots-clés : {keyword_list[:5]}")
        except Exception as e:
            print(f"   [VARIANTS] ⚠️ Erreur : {e} — Utilisation du mot-clé original")
```

### 4g. Limites de sécurité + rotation variantes (dans la boucle `while`, vers la ligne 564)

Remplacer la boucle `while` complète par :

```python
    passe_num = 0
    empty_streak = 0
    keyword_index = 0
    current_keyword = keyword_list[0] if keyword_list else args.keyword
    _STOP_FLAG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'maps_stop.flag')

    while zones_queue and not _objectif_atteint() and passe_num < args.max_passes:
        if os.path.exists(_STOP_FLAG):
            try: os.remove(_STOP_FLAG)
            except: pass
            print("\n   [STOP] Arrêt demandé depuis le dashboard.")
            break

        zone = zones_queue.pop(0)
        if zone.lower() in zones_used: continue
        zones_used.add(zone.lower())
        passe_num += 1

        # Si la zone contient déjà le mot-clé, l'utiliser telle quelle
        # Sinon, combiner mot-clé + zone
        if current_keyword.lower() in zone.lower():
            search_query = zone
        else:
            search_query = f"{current_keyword} {zone}"

        # Taille de la requête pour cette zone
        if MIN_EMAILS_CIBLE:
            manquants  = MIN_EMAILS_CIBLE - emails_count
            limit_zone = min(MAX_PAR_PASSE, max(manquants * 5, 20))
        else:
            limit_zone = min(MAX_PAR_PASSE, effective_limit - len(valid_leads))

        print(f"\n{'='*60}")
        print(f"Passe {passe_num}/{args.max_passes} : {search_query}")
        if MIN_EMAILS_CIBLE:
            print(f"   Emails trouvés : {emails_count}/{MIN_EMAILS_CIBLE}")
        else:
            print(f"   Leads collectés : {len(valid_leads)}/{effective_limit}")
        print(f"{'='*60}")

        try:
            batch_places = await scrape_google_maps(current_keyword, zone, limit_zone,
                                                     known_names=seen_noms_global,
                                                     country=args.country)
            if not batch_places:
                empty_streak += 1
                print(f"   [WARN] Aucun résultat pour '{zone}'. (streak: {empty_streak}/{3})")
                if empty_streak >= 3:
                    print(f"\n   [STOP] 3 zones vides consécutives → arrêt.")
                    break
                continue

            # Reset du streak si on trouve quelque chose
            empty_streak = 0

            # Déduplication
            nouveaux = [p for p in batch_places
                        if p.get('nom', '').strip().lower() not in seen_noms_global
                        and not seen_noms_global.add(p.get('nom', '').strip().lower())]

            print(f"   -> {len(nouveaux)} nouveaux lieux (sur {len(batch_places)} trouvés)")

            for place in nuevos:
                if _objectif_atteint():
                    print(f"\n   [OK] Objectif atteint → arrêt immédiat.")
                    break

                # Filtre min-reviews
                if args.min_reviews > 0 and (place.get('nb_avis') or 0) < args.min_reviews:
                    continue

                lead = await asyncio.to_thread(_enrichir_place, place)
                if lead is None:
                    continue

                # Propager secteur et pays
                if args.secteur:
                    lead['secteur'] = args.secteur
                lead['pays'] = args.country

                # Filtre : avec téléphone OU email si --require-contact
                if args.require_contact and not lead.get('telephone') and not lead.get('email'):
                    continue

                if lead['email']:
                    emails_count += 1

                valid_leads.append(lead)

                # SQLite immédiat
                if _DB_AVAILABLE:
                    try:
                        db_insert_lead(lead)
                    except Exception as e:
                        logger.error(f"SQLite insert_lead({lead['nom']}): {e}")

                if MIN_EMAILS_CIBLE:
                    print(f"   [PROGRESSION] emails={emails_count}/{MIN_EMAILS_CIBLE}  leads={len(valid_leads)}")
                else:
                    print(f"   [PROGRESSION] leads={len(valid_leads)}/{effective_limit}")

                # Direct campaign tracker update
                if args.campaign_id:
                    try:
                        from services.campaign_tracker import update_progress
                        update_progress(
                            args.campaign_id,
                            processed=len(valid_leads),
                            total=effective_limit,
                            emails_found=emails_count,
                            phase='scraping',
                        )
                    except Exception:
                        pass

        except Exception as e:
            print(f"   [ERREUR] Scraping zone '{zone}' : {e}")
            empty_streak += 1
            await asyncio.sleep(3)

        # Si zones_queue est vide et objectif pas atteint : essayer la variante suivante
        if not zones_queue and not _objectif_atteint() and len(keyword_list) > 1:
            keyword_index = (keyword_index + 1) % len(keyword_list)
            if keyword_index != 0:
                current_keyword = keyword_list[keyword_index]
                print(f"\n   [ROTATION] Nouveau mot-clé : '{current_keyword}'")
                # Réinitialiser les zones pour le nouveau mot-clé
                zones_queue = [args.city]
                if args.multi_zone:
                    try:
                        from scraper.zone_agent import get_city_subdivisions
                        sous_zones = get_city_subdivisions(args.city, max_zones=10)
                        zones_queue.extend(sous_zones)
                    except:
                        pass

        # Fallback zones (uniquement hors multi-zone)
        if not zones_queue and not _objectif_atteint() and not args.multi_zone:
            _fallbacks = [
                f"{args.city} centre", f"{args.city} nord", f"{args.city} sud",
                f"{args.city} est", f"{args.city} ouest",
            ]
            _new_zones = [z for z in _fallbacks if z.lower() not in zones_used]
            if _new_zones:
                print(f"\n   [AUTO-ZONE] Ajout de {len(_new_zones)} zones de repli...")
                zones_queue.extend(_new_zones)

        await asyncio.sleep(2)
```

### Vérification
Lancer un test manuel :
```bash
python scraper/main.py --keyword "hôtel" --city "Cotonou" --limit 5 --country bj --require-contact --max-passes 3
```
Vérifier que :
- La locale est `fr-BJ`
- Les leads sans téléphone ni email sont filtrés
- Le scraper s'arrête après 3 passes max
- Les numéros +229 sont correctement extraits

---

## Étape 5 : Campaign Tracker + Scraper Runner

### Objectif
- Passer le `pays` à `create_campaign()`
- Créer automatiquement une liste quand une campagne se termine
- Passer les nouveaux paramètres du scraper au runner

### Fichier : `services/campaign_tracker.py`

#### 5a. Modifier `create_campaign()` (ligne 30)

Remplacer la signature :
```python
def create_campaign(nom: str, secteur: str = '', ville: str = '',
                    source: str = 'maps', nb_demande: int = 0) -> int:
```

Par :
```python
def create_campaign(nom: str, secteur: str = '', ville: str = '',
                    source: str = 'maps', nb_demande: int = 0, pays: str = 'fr') -> int:
```

Et dans le SQL (ligne 39) :
```python
cur = conn.execute("""
    INSERT INTO campagnes (nom, secteur, ville, source, nb_demande, pays, phase, started_at)
    VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
""", (nom, secteur, ville, source, nb_demande, pays, _now()))
```

#### 5b. Ajouter auto-liste dans `complete_campaign()` (ligne 102)

Ajouter avant le `conn.commit()` final :

```python
            # ── Auto-création de liste ───────────────────────────────────
            try:
                camp = conn.execute("SELECT nom, pays FROM campagnes WHERE id=?", (campaign_id,)).fetchone()
                if camp and camp['nom']:
                    flag = "🎯"
                    list_name = f"{flag} {camp['nom']} — {total} leads"
                    cur_list = conn.execute(
                        "INSERT INTO lead_lists (nom, description, icone, campaign_id) VALUES (?, ?, ?, ?)",
                        (list_name, f"Campagne #{campaign_id} ({camp.get('pays','fr')})", flag, campaign_id)
                    )
                    list_id = cur_list.lastrowid
                    leads_rows = conn.execute(
                        "SELECT id FROM leads_bruts WHERE campaign_id=?", (campaign_id,)
                    ).fetchall()
                    for lr in leads_rows:
                        try:
                            conn.execute(
                                "INSERT OR IGNORE INTO lead_list_items (list_id, lead_id) VALUES (?, ?)",
                                (list_id, lr['id'])
                            )
                        except Exception:
                            pass
                    conn.commit()
                    logger.info(f"[TRACKER] Auto-liste #{list_id} créée pour campagne #{campaign_id} ({total} leads)")
            except Exception as e:
                logger.error(f"[TRACKER] Erreur auto-liste : {e}")
```

### Fichier : `services/scraper_runner.py`

#### 5c. Modifier `launch_scraper()` (ligne 22)

Nouvelle signature :
```python
def launch_scraper(keyword, city, sector=None, limit=50, min_emails=10,
                   campaign_name=None, min_reviews=0, multi_zone=False,
                   country='fr', require_contact=False, keyword_variants=False):
```

Dans le corps (ligne 31), ajouter `pays` à `create_campaign` :
```python
camp_id = create_campaign(campaign_name, secteur=sector or keyword,
                          ville=city, source='maps', nb_demande=limit,
                          pays=country)
```

Et modifier le bloc argv (ligne 51) :
```python
        argv = [
            '--keyword', keyword,
            '--city', city,
            '--limit', str(limit),
            '--min-emails', str(min_emails),
            '--campaign-id', str(camp_id),
            '--min-reviews', str(min_reviews),
            '--secteur', str(sector or ''),
            '--country', str(country),
        ]
        if require_contact:
            argv.append('--require-contact')
        if keyword_variants:
            argv.append('--keyword-variants')
        if multi_zone:
            argv.append('--multi-zone')
```

### Vérification
Lancer une campagne depuis le dashboard, vérifier que :
- Le `pays` est bien stocké dans `campagnes`
- Une liste est créée automatiquement dans `lead_lists` quand le scraping est terminé
- Les leads ont le bon `pays` dans `leads_bruts`

---

## Étape 6 : Routes API

### Objectif
Recevoir les nouveaux paramètres (`country`, `require_contact`, `keyword_variants`) depuis l'UI et les passer au scraper.

### Fichier : `dashboard/routes/campaigns.py`

#### 6a. Modifier `api_scraper_launch()` (ligne 14)

Ajouter les nouveaux champs après `min_emails` (ligne 23) :
```python
        country = data.get('country', 'fr').strip()
        require_contact = data.get('require_contact', False)
        keyword_variants = data.get('keyword_variants', False)
```

Et modifier l'appel `launch_scraper` (ligne 29) :
```python
        success, res = launch_scraper(
            keyword=keyword,
            city=city,
            sector=secteur,
            limit=limit,
            min_emails=min_emails,
            campaign_name=campaign_name,
            country=country,
            require_contact=require_contact,
            keyword_variants=keyword_variants
        )
```

### Vérification
Appeler l'API avec :
```bash
curl -X POST http://localhost:5000/api/scraper/launch \
  -H "Content-Type: application/json" \
  -d '{"keyword":"hôtel","city":"Cotonou","limit":5,"country":"bj","require_contact":true}'
```
Vérifier que la campagne est créée avec `pays=bj`.

---

## Étape 7 : UI Sources (formulaire Maps)

### Objectif
Ajouter les champs pays, filtre contact, et variantes LLM au formulaire de lancement Maps.

### Fichier : `dashboard/static/js/modules/sources.js`

#### 7a. Modifier `_formMaps()` (ligne 290)

Remplacer le contenu du `return` par :

```javascript
function _formMaps() {
    return `
    <div class="src-form">
        <div class="src-form-row">
            <label>Secteur / Niche</label>
            ${_renderSectorSelect('maps', 'sf-maps-kw')}
        </div>
        <div class="src-form-row">
            <label>Mot-clé Google Maps</label>
            <input id="sf-maps-kw" type="text" placeholder="plombier, avocat, hôtel..." class="inp">
        </div>
        <div class="src-form-row">
            <label>Ville</label>
            <input id="sf-maps-city" type="text" placeholder="Paris, Cotonou, Lyon..." class="inp">
        </div>
        <div class="src-form-row">
            <label>Pays</label>
            <select id="sf-maps-country" class="inp">
                <option value="fr">France</option>
                <option value="bj">Bénin</option>
                <option value="be">Belgique</option>
                <option value="ch">Suisse</option>
                <option value="lu">Luxembourg</option>
            </select>
        </div>
        <div class="src-form-row" style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
            <div>
                <label>Nombre de leads</label>
                <input id="sf-maps-limit" type="number" value="20" min="1" max="200" class="inp">
            </div>
            <div>
                <label>Emails min.</label>
                <input id="sf-maps-min-emails" type="number" value="5" min="0" class="inp">
            </div>
        </div>
        <div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:4px">
            <label style="display:flex;align-items:center;gap:6px;font-size:12px;cursor:pointer">
                <input type="checkbox" id="sf-maps-multi" checked> Multi-zones
            </label>
            <label style="display:flex;align-items:center;gap:6px;font-size:12px;cursor:pointer">
                <input type="checkbox" id="sf-maps-contact" checked> Avec tél. ou email
            </label>
            <label style="display:flex;align-items:center;gap:6px;font-size:12px;cursor:pointer">
                <input type="checkbox" id="sf-maps-variants"> Variantes LLM
            </label>
        </div>
        <div id="sf-maps-log" class="src-log" style="display:none"></div>
        <div class="src-form-actions">
            <button class="btn accent" onclick="sourcesLaunch('maps')">Lancer Maps</button>
        </div>
    </div>`;
}
```

#### 7b. Modifier `_launchMaps()` (ligne 534)

Remplacer la fonction par :

```javascript
async function _launchMaps() {
    const kw      = document.getElementById('sf-maps-kw')?.value?.trim();
    const city    = document.getElementById('sf-maps-city')?.value?.trim() || '';
    const sector  = document.getElementById('sf-maps-sector')?.value || '';
    const limit   = parseInt(document.getElementById('sf-maps-limit')?.value) || 20;
    const minMails= parseInt(document.getElementById('sf-maps-min-emails')?.value) || 0;
    const country = document.getElementById('sf-maps-country')?.value || 'fr';
    const requireContact = document.getElementById('sf-maps-contact')?.checked || false;
    const keywordVariants = document.getElementById('sf-maps-variants')?.checked || false;

    if (!kw) { _srcLog('maps', '⚠ Mot-clé requis'); _setSourceRunning('maps', false); return; }

    const body = {
        keyword: kw, city, sector, limit,
        min_emails: minMails, country,
        require_contact: requireContact,
        keyword_variants: keywordVariants
    };

    const r = await fetch('/api/scraper/launch', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(body),
    });
    const d = await r.json();
    if (d.error) { _srcLog('maps', `✗ ${d.error}`); _setSourceRunning('maps', false); return; }
    _srcLog('maps', `✓ Campagne #${d.campaign_id} lancée — ${kw} · ${city} (${country})`);
    _srcPollUntilDone('maps', '/api/scraper/status');
}
```

### Vérification
Ouvrir le dashboard → Sources → Google Maps. Vérifier que :
- Le sélecteur Pays apparaît (France, Bénin, Belgique, Suisse, Luxembourg)
- La checkbox "Avec tél. ou email" est cochée par défaut
- La checkbox "Variantes LLM" est disponible
- Le lancement fonctionne avec les nouveaux params

---

## Étape 8 : insert_lead — Stocker `pays`

### Objectif
S'assurer que le champ `pays` est bien stocké quand un lead est inséré ou mis à jour.

### Fichier : `database/leads.py`

#### 8a. Modifier `insert_lead()` (ligne 18)

Dans le bloc INSERT (vers la ligne 99), ajouter `pays` :

```python
        cur = conn.execute("""
            INSERT INTO leads_bruts
            (campaign_id, nom, adresse, site_web, telephone, email,
             email_valide, rating, nb_avis, category,
             mot_cle, ville, lien_maps, logo_url,
             source, tag_urgence, niveau_urgence, donnees_audit,
             secteur, pays)
            VALUES
            (:campaign_id, :nom, :adresse, :site_web, :telephone, :email,
             :email_valide, :rating, :nb_avis, :category,
             :mot_cle, :ville, :lien_maps, :logo_url,
             :source, :tag_urgence, :niveau_urgence, :donnees_audit,
             :secteur, :pays)
        """, {
            ...
            'secteur':        lead.get('secteur'),
            'pays':           lead.get('pays', 'fr'),  # ← AJOUTER
        })
```

Dans le bloc UPDATE doublon (vers la ligne 86), ajouter :

```python
                # Mise à jour du pays si manquant
                if lead.get('pays') and not existing.get('pays'):
                    updates['pays'] = lead['pays']
```

### Vérification
Lancer un scraping, vérifier en DB :
```sql
SELECT id, nom, ville, pays FROM leads_bruts ORDER BY id DESC LIMIT 10;
```
La colonne `pays` doit contenir 'fr' ou 'bj' selon la campagne.

---

## Résumé de tous les fichiers modifiés

| # | Fichier | Action |
|---|---------|--------|
| 1 | `database/schema.py` | Migration `pays` |
| 2 | `core/city_rotator.py` | Villes béninoises |
| 3 | `scraper/keyword_variants.py` | **Nouveau** — Variantes LLM |
| 4 | `scraper/main.py` | `--country`, locale, regex, blacklist, `--require-contact`, `--max-passes`, `--keyword-variants`, safety limits |
| 5 | `services/campaign_tracker.py` | `pays` dans `create_campaign()`, auto-liste dans `complete_campaign()` |
| 6 | `services/scraper_runner.py` | Passer `country`, `require_contact`, `keyword_variants` |
| 7 | `dashboard/routes/campaigns.py` | Recevoir les nouveaux params |
| 8 | `dashboard/static/js/modules/sources.js` | Formulaire Maps : pays, checkboxes |
| 9 | `database/leads.py` | `insert_lead()` stocker `pays` |

---

## Tests de vérification

### Test 1 : Scraping France avec filtre contact
```bash
python scraper/main.py --keyword "restaurant" --city "Paris" --limit 10 --country fr --require-contact --max-passes 3
```
→ Vérifier que tous les leads ont un tél OU un email.

### Test 2 : Scraping Bénin
```bash
python scraper/main.py --keyword "hôtel" --city "Cotonou" --limit 10 --country bj --require-contact
```
→ Vérifier que la locale est fr-BJ, les numéros +229 sont trouvés.

### Test 3 : Variantes LLM
```bash
python scraper/main.py --keyword "hôtel" --city "Cotonou" --limit 10 --country bj --keyword-variants --max-passes 5
```
→ Vérifier que le scraper essaie plusieurs variantes (bnb, auberge, guest house...).

### Test 4 : Auto-liste
Lancer une campagne depuis le dashboard, attendre la fin, vérifier dans l'onglet Listes qu'une liste "🎯 Nom campagne — X leads" a été créée.

### Test 5 : Arrêt sécurité
Lancer avec `--max-passes 2` sur une ville sans résultats. Vérifier que le scraper s'arrête après 2 passes.
