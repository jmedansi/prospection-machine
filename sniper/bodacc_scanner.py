# -*- coding: utf-8 -*-
"""
sniper/bodacc_scanner.py — Source BODACC : nominations de dirigeants

Lire sniper/BODACC_SCANNER_README.md avant toute modification.

Scanne le BODACC quotidiennement pour détecter les nouvelles nominations de
dirigeants dans des entreprises B2B digitales. Injecte les leads qualifiés
dans leads_bruts avec source='bodacc'.

Usage programmatique :
    from sniper.bodacc_scanner import scan_daily
    result = scan_daily()  # scanne hier
    result = scan_daily("2026-04-10")  # date explicite
"""

import json
import logging
import re
import time
from datetime import date, timedelta
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

logger = logging.getLogger(__name__)

# ─── Constantes ──────────────────────────────────────────────────────────────

BODACC_API = (
    "https://bodacc-datadila.opendatasoft.com"
    "/api/explore/v2.1/catalog/datasets/annonces-commerciales/records"
)

SIRENE_API = "https://recherche-entreprises.api.gouv.fr/search"

# Codes NAF ciblés — entreprises B2B digitales / tech / consulting
# (Source : INSEE nomenclature NAF Rev. 2)
TARGET_NAF = {
    # Informatique et tech
    "6201Z",  # Programmation informatique
    "6202A",  # Conseil en systèmes informatiques
    "6202B",  # Tierce maintenance
    "6203Z",  # Gestion d'installations informatiques
    "6209Z",  # Autres activités informatiques
    # Hébergement / cloud / data
    "6311Z",  # Traitement de données, hébergement
    "6312Z",  # Portails Internet
    "6391Z",  # Agences de presse
    # Publicité / marketing / agences
    "7311Z",  # Agences de publicité
    "7312Z",  # Régie publicitaire
    "7320Z",  # Études de marché
    # Conseil en management / stratégie
    "7022Z",  # Conseil pour les affaires et la gestion
    "7021Z",  # Relations publiques
    "7490B",  # Autres activités spécialisées
    # Commerce gros IT
    "4651Z",  # Commerce de gros — ordinateurs
    "4652Z",  # Commerce de gros — composants électroniques
    # Télécoms
    "6110Z",  # Télécommunications filaires
    "6120Z",  # Télécommunications sans fil
    "6190Z",  # Autres télécommunications
    # Édition / médias digitaux
    "5821Z",  # Édition de jeux électroniques
    "5829A",  # Édition de logiciels systèmes
    "5829B",  # Édition de logiciels outils
    "5829C",  # Édition de logiciels applicatifs
}

# Qualités de dirigeants ciblées — liste exhaustive des valeurs BODACC réelles.
# Utiliser _is_ceo_qualite() pour comparer (normalisation Unicode).
_CEO_QUALITES = {
    "president",
    "directeur general",
    "gerant",
    "ceo",
    "pdg",
    "fondateur",
    "co-fondateur",
    "cofondateur",
    "associe gerant",
    "administrateur delegue",
    "directeur general delegue",
    "president directeur general",
    "gerant associe",
    "dirigeant",
    "representant legal",
}

# Requête BODACC : créations + modifications diverses
# Note : typeavis vaut toujours 'annonce' — le vrai filtre est familleavis_lib
# Note : la date doit être au format date'YYYY-MM-DD' (syntaxe ODS)
_BODACC_WHERE_TMPL = (
    "dateparution=date'{date}' AND "
    "(familleavis_lib='Créations' OR familleavis_lib='Modifications diverses')"
)

def _norm_qualite(text: str) -> str:
    """Normalise une qualité BODACC : minuscules + sans accents."""
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", text.lower().strip())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _is_ceo_qualite(qualite_raw: str) -> bool:
    """Vérifie si la qualité est celle d'un décideur (correspondance exacte normalisée)."""
    return _norm_qualite(qualite_raw) in _CEO_QUALITES


_PAGE_SIZE = 100
_REQUEST_TIMEOUT = 15
_INTER_REQUEST_DELAY = 0.1   # secondes entre pages (politesse)


# ─── Parsing BODACC ──────────────────────────────────────────────────────────

def _extract_siren(registre) -> Optional[str]:
    """
    Extrait le SIREN (9 chiffres) depuis le champ `registre` BODACC.
    Le champ est une liste : ['103424180', '103 424 180'] — index 0 = SIREN brut.
    Exemples :
      ['103424180', '103 424 180']  → "103424180"
      "399085557 RCS Paris"         → "399085557"
    """
    if not registre:
        return None
    if isinstance(registre, list):
        registre = registre[0] if registre else ""
    if not registre:
        return None
    m = re.search(r"\b(\d{9})\b", str(registre))
    return m.group(1) if m else None


def _parse_ceo_from_commercant(commercant: str) -> Optional[dict]:
    """
    Extrait le prénom/nom depuis le champ `commercant` pour les Créations.
    Format BODACC : "NOM, Prénom, autre info, ..."
    Exemple : "CHERY, Quentin, ..."  → {prenom: "Quentin", nom: "Chery", qualite: "gerant"}
    Retourne None si le format n'est pas reconnu.
    """
    if not commercant or not isinstance(commercant, str):
        return None
    parts = [p.strip() for p in commercant.split(",")]
    if len(parts) < 2:
        return None
    nom = parts[0].strip().title()
    prenom_raw = parts[1].strip()
    prenom = prenom_raw.split()[0].capitalize() if prenom_raw else ""
    if not nom or not prenom:
        return None
    return {"prenom": prenom, "nom": nom, "qualite": "gerant"}


def _parse_dirigeants(acte_raw) -> list[dict]:
    """
    Extrait la liste des dirigeants depuis le champ `acte` BODACC.
    `acte_raw` peut être un dict ou une chaîne JSON.
    Retourne une liste de dicts {prenom, nom, qualite}.
    """
    if not acte_raw:
        return []

    # `acte` arrive parfois sérialisé en string
    if isinstance(acte_raw, str):
        try:
            acte = json.loads(acte_raw)
        except json.JSONDecodeError:
            return []
    else:
        acte = acte_raw

    dirigeants_raw = acte.get("dirigeants") or acte.get("representants") or []
    if not isinstance(dirigeants_raw, list):
        dirigeants_raw = [dirigeants_raw]

    result = []
    for d in dirigeants_raw:
        if not isinstance(d, dict):
            continue
        # Personnes physiques seulement (type == "pp")
        if d.get("type") and d.get("type").lower() not in ("pp", "personne physique"):
            continue
        nom = (d.get("nom") or "").strip().title()
        prenoms_raw = (d.get("prenoms") or d.get("prenom") or "").strip()
        prenom = prenoms_raw.split()[0].capitalize() if prenoms_raw else ""
        qualite = (d.get("qualite") or "").lower().strip()

        if not nom or not prenom:
            continue

        # Vérifier que la qualité est celle d'un décideur (correspondance exacte)
        if not _is_ceo_qualite(qualite):
            continue

        result.append({"prenom": prenom, "nom": nom, "qualite": qualite})

    return result


# ─── Résolution SIREN → données entreprise ───────────────────────────────────

def _resolve_company(siren: str) -> Optional[dict]:
    """
    Résout un SIREN via l'API recherche-entreprises.api.gouv.fr.
    Retourne {nom, naf, site_web, ville} ou None si non trouvé.
    """
    try:
        resp = requests.get(
            SIRENE_API,
            params={"q": siren, "per_page": 1},
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.debug(f"SIRENE API — SIREN {siren} : {e}")
        return None

    results = data.get("results") or []
    if not results:
        return None

    c = results[0]
    siege = c.get("siege") or {}

    # Rejeter les entreprises RGPD opt-out — aucune donnée utilisable
    nom = c.get("nom_raison_sociale") or c.get("nom_complet") or ""
    if "[NON-DIFFUSIBLE]" in nom or nom.strip() == "":
        logger.debug(f"SIRENE — SIREN {siren} : données non diffusibles, ignoré")
        return None

    naf = (
        siege.get("activite_principale")
        or c.get("activite_principale")
        or ""
    ).replace(".", "").upper()[:5]

    # Rejeter les entrepreneurs individuels sans employés (effectif 0 ou null)
    # SIRENE: tranche_effectif "00"=0 sal., "01"=1-2, "02"=3-5, "03"=6-9, etc.
    # On accepte dès qu'il y a un effectif déclaré ≥ "01" (ou non renseigné = on garde)
    tranche = c.get("tranche_effectif_salarie") or siege.get("tranche_effectif_salarie") or ""
    if tranche == "00":
        logger.debug(f"SIRENE — SIREN {siren} ({nom}) : 0 salarié, ignoré")
        return None

    site_web = (siege.get("site_internet") or "").strip().rstrip("/")
    if site_web and not site_web.startswith("http"):
        site_web = "https://" + site_web

    return {
        "nom":      nom,
        "naf":      naf,
        "site_web": site_web,
        "ville":    siege.get("commune") or siege.get("libelle_commune") or "",
        "siren":    siren,
    }


# ─── Insertion en base ────────────────────────────────────────────────────────

def _insert_bodacc_lead(
    company: dict,
    ceo: dict,
    raw_record: dict,
    conn=None,
) -> Optional[int]:
    """
    Insère un lead BODACC dans leads_bruts.
    Retourne lead_id ou None si déjà présent (doublon sur SIREN).
    Si conn est fourni, l'utilise (pour batch insert). Sinon, ouvre sa propre connexion.
    """
    from database.connection import get_conn

    siren    = company["siren"]
    nom      = company["nom"]
    site_web = company.get("site_web") or ""
    ville    = company.get("ville") or ""
    naf      = company.get("naf") or ""

    prenom = ceo["prenom"]
    nom_ceo = ceo["nom"]

    # Données JSON pour le CEO (injectées dans donnees_audit)
    donnees = json.dumps({
        "ceo_prenom":  prenom,
        "ceo_nom":     nom_ceo,
        "ceo_source":  "bodacc",
        "naf":         naf,
        "siren":       siren,
        "qualite":     ceo.get("qualite", ""),
        "bodacc_date": raw_record.get("dateparution", ""),
        "bodacc_type": raw_record.get("typeavis", ""),
    }, ensure_ascii=False)

    def _do_insert(c):
        existing = c.execute(
            "SELECT id FROM leads_bruts WHERE donnees_audit LIKE ? AND source='bodacc' AND statut NOT IN ('archive','desabonne')",
            (f'%"siren": "{siren}"%',)
        ).fetchone()
        if existing:
            logger.debug(f"BODACC — SIREN {siren} déjà en base (id={existing[0]})")
            return None

        cursor = c.execute("""
            INSERT INTO leads_bruts
              (nom, adresse, ville, site_web, telephone, email,
               mot_cle, category, source,
               tag_urgence, niveau_urgence, donnees_audit, statut)
            VALUES
              (?, '', ?, ?, '', '',
               ?, ?, 'bodacc',
               NULL, 0, ?, 'en_attente')
        """, (
            f"{prenom} {nom_ceo} — {nom}",
            ville,
            site_web,
            f"Dirigeant BODACC — {naf}",
            f"CEO {naf}",
            donnees,
        ))
        return cursor.lastrowid

    try:
        if conn:
            lead_id = _do_insert(conn)
        else:
            with get_conn() as c:
                lead_id = _do_insert(c)
                c.commit()

        if lead_id:
            logger.info(f"BODACC — lead inséré {prenom} {nom_ceo} / {nom} (SIREN {siren}) → id={lead_id}")
        return lead_id

    except Exception as e:
        logger.error(f"BODACC — insert échoué SIREN {siren} : {e}")
        return None


# ─── Fetch BODACC ─────────────────────────────────────────────────────────────

def _fetch_records(target_date: str) -> list[dict]:
    """
    Récupère tous les enregistrements BODACC pour `target_date` avec pagination.
    """
    records = []
    offset  = 0
    where   = _BODACC_WHERE_TMPL.format(date=target_date)

    while True:
        try:
            resp = requests.get(
                BODACC_API,
                params={
                    "select":  "registre,commercant,tribunal,ville,cp,typeavis,familleavis_lib,acte,dateparution",
                    "where":   where,
                    "limit":   _PAGE_SIZE,
                    "offset":  offset,
                    "order_by": "dateparution DESC",
                },
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            page = resp.json()
        except Exception as e:
            logger.error(f"BODACC API — page offset={offset} : {e}")
            break

        batch = page.get("results") or []
        records.extend(batch)

        total_count = page.get("total_count", 0)
        offset += len(batch)

        if offset >= total_count or not batch:
            break

        time.sleep(_INTER_REQUEST_DELAY)

    return records


# ─── Point d'entrée principal ─────────────────────────────────────────────────

def scan_daily(target_date: Optional[str] = None) -> dict:
    """
    Scanne le BODACC pour `target_date` (défaut : hier).

    Flux :
      1. Fetch BODACC (Modification + Inscription du jour)
      2. Pour chaque annonce : extraire SIREN + dirigeant
      3. Filtrer par code NAF (B2B digital seulement)
      4. Résoudre SIREN → données entreprise (API gouv.fr)
      5. Insérer dans leads_bruts si site_web présent

    Returns:
        {
          "date":     "2026-04-10",
          "scanned":  int,   # total annonces BODACC lues
          "filtered": int,   # après filtre NAF + dirigeant
          "inserted": int,   # leads créés en base
          "skipped":  int,   # doublons ou sans site_web
          "errors":   int,
        }
    """
    if target_date is None:
        target_date = (date.today() - timedelta(days=1)).isoformat()

    logger.info(f"BODACC scan — date={target_date}")

    stats = {
        "date":     target_date,
        "scanned":  0,
        "filtered": 0,
        "inserted": 0,
        "skipped":  0,
        "errors":   0,
    }

    # ── 1. Fetch ──────────────────────────────────────────────────────────────
    records = _fetch_records(target_date)
    stats["scanned"] = len(records)
    logger.info(f"BODACC — {len(records)} annonces récupérées pour {target_date}")

    if not records:
        return stats

    # ── 2. Parse tous les enregistrements (sans résoudre SIRENE) ────────────
    candidates = []  # (siren, dirigeants, record)
    for record in records:
        try:
            siren = _extract_siren(record.get("registre") or "")
            if not siren:
                stats["skipped"] += 1
                continue
            dirigeants = _parse_dirigeants(record.get("acte"))
            if not dirigeants:
                ceo_from_commercant = _parse_ceo_from_commercant(record.get("commercant") or "")
                if ceo_from_commercant:
                    dirigeants = [ceo_from_commercant]
            if not dirigeants:
                stats["skipped"] += 1
                continue
            candidates.append((siren, dirigeants, record))
        except Exception as e:
            logger.error(f"BODACC — erreur parsing record : {e}")
            stats["errors"] += 1

    # ── 3. Résoudre les SIREN en parallèle ──────────────────────────────────
    siren_to_company: dict[str, Optional[dict]] = {}
    with ThreadPoolExecutor(max_workers=10) as pool:
        fut_map = {pool.submit(_resolve_company, s): s for s, _, _ in candidates}
        for fut in as_completed(fut_map):
            siren = fut_map[fut]
            try:
                siren_to_company[siren] = fut.result()
            except Exception as e:
                logger.error(f"BODACC — SIRENE {siren}: {e}")
                siren_to_company[siren] = None

    # ── 4. Filtrer + insérer en batch ───────────────────────────────────────
    leads_to_insert = []  # (company, ceo, record) tuples
    inserted_count = 0
    skipped_count = 0
    filtered_count = 0

    for siren, dirigeants, record in candidates:
        company = siren_to_company.get(siren)
        if not company:
            skipped_count += 1
            continue
        naf = company.get("naf", "")
        if naf not in TARGET_NAF:
            skipped_count += 1
            continue
        filtered_count += 1
        leads_to_insert.append((company, dirigeants[0], record))

    stats["filtered"] = filtered_count

    # ── 5. Batch insert ─────────────────────────────────────────────────────
    if leads_to_insert:
        from database.connection import get_conn
        with get_conn() as conn:
            for company, ceo, record in leads_to_insert:
                try:
                    lead_id = _insert_bodacc_lead(company, ceo, record, conn=conn)
                    if lead_id:
                        inserted_count += 1
                    else:
                        skipped_count += 1
                except Exception as e:
                    logger.error(f"BODACC — erreur insertion lead : {e}")
                    stats["errors"] += 1
            conn.commit()

    stats["inserted"] = inserted_count
    stats["skipped"] = stats.get("skipped", 0) + skipped_count

    logger.info(
        f"BODACC scan terminé — "
        f"{stats['scanned']} lus | {stats['filtered']} filtrés | "
        f"{stats['inserted']} insérés | {stats['skipped']} ignorés | "
        f"{stats['errors']} erreurs"
    )
    return stats
