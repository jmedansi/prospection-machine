# -*- coding: utf-8 -*-
"""
sniper/enrichment/ceo_finder.py — Identification du décideur (CEO/Fondateur)

Lire sniper/enrichment/README.md avant toute modification.

Stratégie en 2 étapes :
  1. Primaire  : Google dork via SerpApi (si SERPAPI_KEY dans .env)
                 Requête : site:linkedin.com/in ("CEO" OR "Fondateur" OR "Gérant") "Nom entreprise"
                 Extrait prénom/nom depuis le <title> du résultat
  2. Fallback  : Scraping mentions légales + Ollama local
                 (enrichisseur/ceo_finder.py existant — réutilisé)

Normalisation : suppression accents, minuscules, sans caractères spéciaux
→ Prêt pour la génération de permutations email
"""

import re
import logging
import unicodedata
from typing import Optional

logger = logging.getLogger(__name__)

# Sentinel retourné par _find_via_* quand le modèle est indisponible (quota/connexion).
# Distingue "introuvable" (None) de "pas pu essayer" (_QUOTA_ERROR).
_QUOTA_ERROR = object()

# Titres LinkedIn cibles (ordre de priorité)
_TARGET_TITLES = [
    "fondateur", "co-fondateur", "cofondateur",
    "ceo", "président", "president",
    "directeur général", "directeur general", "dg",
    "gérant", "gerant", "dirigeant",
    "directeur", "associé", "associe",
]


def _normalize(text: str) -> str:
    """Supprime accents, met en minuscules, retire les caractères spéciaux."""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_str = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[^a-z\-]", "", ascii_str.lower())


def _parse_linkedin_title(title: str) -> Optional[tuple[str, str]]:
    """
    Parse un titre LinkedIn du type :
      "Jean Dupont - Gérant - Nom Boite | LinkedIn"
      "Marie Martin – CEO chez Entreprise | LinkedIn"

    Retourne (prenom, nom) ou None.
    """
    # Nettoyer "| LinkedIn" en fin
    title = re.sub(r"\s*\|\s*LinkedIn.*$", "", title, flags=re.IGNORECASE).strip()

    # Séparateurs : " - ", " – ", " | "
    parts = re.split(r"\s+[-–|]\s+", title)
    if not parts:
        return None

    # Le nom complet est toujours en première position
    full_name = parts[0].strip()

    # Vérifier que la 2ème partie contient un titre cible
    if len(parts) >= 2:
        role_part = parts[1].lower()
        if not any(t in role_part for t in _TARGET_TITLES):
            return None  # Ce n'est pas un décideur

    # Extraire prénom / nom (2 mots minimum)
    name_parts = full_name.split()
    if len(name_parts) < 2:
        return None

    prenom = name_parts[0].capitalize()
    nom    = " ".join(name_parts[1:]).upper()
    return prenom, nom


def _find_via_api_gouv(domain: str) -> Optional[tuple[str, str]]:
    """
    Cherche le dirigeant via l'API recherche-entreprises.api.gouv.fr (INSEE + INPI).

    Stratégie :
      1. Cherche par domaine (site_web) → SIREN
      2. Extrait le dirigeant le plus pertinent (Président, DG, Gérant, PDG)
      3. Cross-valide que l'entreprise n'est pas liquidée

    Fonctionne uniquement pour les entreprises françaises immatriculées.
    Pas de clé API requise.
    """
    try:
        import requests

        # Normalise le domaine pour la recherche (retire www., TLD)
        clean_domain = re.sub(r"^www\.", "", domain.lower()).split(".")[0]

        resp = requests.get(
            "https://recherche-entreprises.api.gouv.fr/search",
            params={"q": clean_domain, "page": 1, "per_page": 5},
            timeout=8,
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results", [])
        if not results:
            logger.debug(f"api_gouv: aucun résultat pour {clean_domain}")
            return None

        for company in results:
            # Vérifier que la société est active
            etat = company.get("matching_etablissements", [{}])[0].get("etat_administratif", "")
            if etat == "F":  # Fermé
                continue

            # Chercher le dirigeant dans les mandataires sociaux (INPI)
            dirigeants = company.get("dirigeants", [])
            if not dirigeants:
                continue

            # Priorité : Président > DG > PDG > Gérant > Directeur
            _PRIORITY = ["président", "directeur général", "pdg", "gérant", "directeur", "associé"]
            best = None
            best_score = 99

            for d in dirigeants:
                qualite = (d.get("qualite") or "").lower()
                # L'API retourne "prenoms" (peut contenir plusieurs prénoms)
                prenoms_raw = (d.get("prenoms") or d.get("prenom") or "").strip()
                # Garder uniquement le premier prénom
                prenom = prenoms_raw.split()[0].capitalize() if prenoms_raw else ""
                nom = (d.get("nom") or "").strip()

                if not prenom or not nom:
                    continue  # Personnes morales (holdings) ignorées

                for i, title in enumerate(_PRIORITY):
                    if title in qualite:
                        if i < best_score:
                            best_score = i
                            best = (prenom.capitalize(), nom.upper())
                        break
                else:
                    # Aucun titre prioritaire mais c'est quand même un dirigeant
                    if best is None:
                        best = (prenom.capitalize(), nom.upper())

            if best:
                logger.info(f"api_gouv: {domain} -> {best[0]} {best[1]}")
                return best

    except Exception as e:
        logger.debug(f"api_gouv: erreur pour {domain} — {e}")

    return None


def _scrape_legal_page(url: str) -> str:
    """
    Récupère le texte brut des pages mentions légales / à propos du site.
    Retourne une chaîne vide si inaccessible.
    """
    import requests
    from bs4 import BeautifulSoup

    candidates = [
        url.rstrip("/") + "/mentions-legales",
        url.rstrip("/") + "/mentions_legales",
        url.rstrip("/") + "/a-propos",
        url.rstrip("/") + "/about",
        url.rstrip("/") + "/cgv",
        url.rstrip("/") + "/contact",
    ]

    for page_url in candidates:
        try:
            r = requests.get(page_url, timeout=6, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200 and len(r.text) > 200:
                soup = BeautifulSoup(r.text, "html.parser")
                # Retirer scripts/styles
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                text = soup.get_text(separator=" ", strip=True)
                if len(text) > 100:
                    return text[:3000]  # Max 3000 chars pour Groq
        except Exception:
            continue

    return ""


def _find_via_groq(url: str, company_name: str, domain: str) -> Optional[tuple[str, str]]:
    """
    Fallback Groq : scrape les mentions légales + LLM cloud pour extraire le dirigeant.

    Plus fiable qu'Ollama (pas de dépendance locale) et plus rapide.
    Requiert GROQ_API_KEY dans .env — plan gratuit suffisant (rate limit : 30 req/min).
    """
    import os
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.debug("ceo_finder Groq: GROQ_API_KEY absent")
        return None

    try:
        page_text = _scrape_legal_page(url) if url else ""

        if not page_text:
            # Pas de page légale accessible — demande à Groq avec juste le nom
            prompt = (
                f"Quel est le nom du dirigeant principal (PDG, CEO, Gérant, Fondateur, "
                f"Administrateur Général, Président du Conseil) "
                f"de l'entreprise '{company_name}' (domaine: {domain}) ? "
                f"Réponds uniquement avec: PRENOM NOM. Si inconnu, réponds: INCONNU."
            )
        else:
            prompt = (
                f"Voici le texte d'une page de mentions légales d'une entreprise "
                f"nommée '{company_name}' ({domain}).\n\n"
                f"Texte : {page_text}\n\n"
                f"Extrais le nom complet du dirigeant principal "
                f"(Gérant, Président, PDG, CEO, Directeur Général, Fondateur, "
                f"Administrateur Général). "
                f"Réponds uniquement avec: PRENOM NOM (ex: Jean DUPONT). "
                f"Si introuvable, réponds: INCONNU."
            )

        from groq import Groq
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model    = "llama-3.1-8b-instant",   # rapide et gratuit
            messages = [{"role": "user", "content": prompt}],
            max_tokens  = 20,
            temperature = 0,
        )

        answer = response.choices[0].message.content.strip().upper()
        logger.debug(f"ceo_finder Groq raw: '{answer}'")

        _REFUSALS = ("INCONNU", "JE N", "JE NE", "AUCUN", "INTROUVABLE", "PAS D", "DESOLÉ", "SORRY", "I DON", "I CAN")
        if any(answer.startswith(r) for r in _REFUSALS) or len(answer) < 4:
            return None

        # Nettoyer les artefacts ("PRENOM NOM:", "Le dirigeant est: ...")
        answer = re.sub(r"^[^A-ZÀÂÉÈÊËÎÏÔÙÛÜ]+", "", answer)
        parts = answer.split()
        if len(parts) < 2:
            return None

        prenom = parts[0].capitalize()
        nom    = " ".join(parts[1:]).upper()

        # Sanity check : rejeter les réponses génériques
        _JUNK = {"PRENOM", "NOM", "DIRIGEANT", "INCONNU", "GÉRANT", "PRESIDENT"}
        if prenom.upper() in _JUNK or nom.upper() in _JUNK:
            return None

        logger.info(f"ceo_finder Groq: {domain} -> {prenom} {nom}")
        return prenom, nom

    except Exception as e:
        err = str(e).lower()
        if any(k in err for k in ("rate", "429", "quota", "limit", "too many")):
            logger.warning(f"ceo_finder Groq: quota épuisé — {e}")
            return _QUOTA_ERROR
        logger.warning(f"ceo_finder Groq: erreur pour {domain} — {e}")

    return None


def _find_via_ollama(url: str, domain: str):
    """Fallback : utilise le ceo_finder existant (Ollama + mentions légales)."""
    try:
        import sys, os
        ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)
        ))))
        if ROOT not in sys.path:
            sys.path.insert(0, ROOT)

        from enrichisseur.ceo_finder import find_ceo_from_url
        prenom, nom = find_ceo_from_url(url)
        if prenom and nom:
            logger.info(f"ceo_finder Ollama: {domain} -> {prenom} {nom}")
            return prenom, nom
    except (ConnectionRefusedError, OSError) as e:
        logger.warning(f"ceo_finder Ollama: modèle indisponible — {e}")
        return _QUOTA_ERROR
    except Exception as e:
        err = str(e).lower()
        if any(k in err for k in ("connection", "refused", "timeout", "unavailable")):
            logger.warning(f"ceo_finder Ollama: indisponible — {e}")
            return _QUOTA_ERROR
        logger.debug(f"ceo_finder Ollama: non disponible — {e}")

    return None


def find_ceo(
    company_name: str,
    domain: str,
    url: Optional[str] = None,
    pays: str = "fr",
) -> dict:
    """
    Trouve le décideur d'une entreprise.

    Args:
        company_name: Nom de l'entreprise (ex: "Dupont Solar")
        domain:       Domaine (ex: "dupont-solar.fr")
        url:          URL complète pour le fallback Ollama
        pays:         Code pays ISO (défaut: "fr"). "bj" pour Bénin — bypass API gouv.fr.

    Returns:
        {
            "ceo_prenom":    str | None,
            "ceo_nom":       str | None,
            "ceo_prenom_norm": str | None,  # normalisé pour permutations
            "ceo_nom_norm":    str | None,
            "ceo_source":    str,  # 'api_gouv' | 'groq' | 'ollama' | 'not_found'
        }
    """
    import os
    from core.config import ensure_env
    ensure_env()

    result = {
        "ceo_prenom":      None,
        "ceo_nom":         None,
        "ceo_prenom_norm": None,
        "ceo_nom_norm":    None,
        "ceo_source":      "not_found",
    }

    quota_hit = False  # True si Groq ou Ollama ont échoué par quota/indisponibilité

    # ── 1. API gouv.fr (INSEE + INPI — gratuit, sans clé, FR uniquement) ────────
    if pays == "fr":
        found = _find_via_api_gouv(domain)
    else:
        found = None
    if found and found is not _QUOTA_ERROR:
        result["ceo_prenom"] = found[0]
        result["ceo_nom"]    = found[1]
        result["ceo_source"] = "api_gouv"

    # ── 2. Groq (scrape mentions légales + LLM cloud — GROQ_API_KEY requis) ────
    if not result["ceo_prenom"] and url:
        found = _find_via_groq(url, company_name, domain)
        if found is _QUOTA_ERROR:
            quota_hit = True
        elif found:
            result["ceo_prenom"] = found[0]
            result["ceo_nom"]    = found[1]
            result["ceo_source"] = "groq"

    # ── 3. Ollama (LLM local — fallback si Groq absent/indisponible) ──────────
    if not result["ceo_prenom"] and url:
        found = _find_via_ollama(url, domain)
        if found is _QUOTA_ERROR:
            quota_hit = True
        elif found:
            result["ceo_prenom"] = found[0]
            result["ceo_nom"]    = found[1]
            result["ceo_source"] = "ollama"

    # ── Normalisation pour les permutations ───────────────────────────────────
    if result["ceo_prenom"]:
        result["ceo_prenom_norm"] = _normalize(result["ceo_prenom"])
    if result["ceo_nom"]:
        result["ceo_nom_norm"] = _normalize(result["ceo_nom"])

    # ── Notification + marquage retry uniquement sur quota/indisponibilité ─────
    if not result["ceo_prenom"] and quota_hit:
        result["ceo_source"] = "quota_error"
        logger.warning(f"ceo_finder: quota/modèle indisponible pour {company_name} ({domain})")
        try:
            from core.telegram_adapter import notify
            notify(
                "CEO — quota modèle épuisé",
                f"*{company_name}* — `{domain}`\n"
                f"Groq ou Ollama indisponible (quota/connexion).\n"
                f"Relance automatique dans 2h.",
            )
        except Exception:
            pass

    return result
