# -*- coding: utf-8 -*-
"""
enrichisseur/extract_responsables_ml.py

Pipeline :
  leads_bruts (ml_extracted vide, site_web non vide)
    → requests (homepage → lien ML) ou fallback Playwright
    → 500 premiers mots → stocke raw_text dans leads_bruts.ml_extracted (JSON)
"""

import json
import sys
import os
from typing import Optional
from urllib.parse import urljoin

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests
from bs4 import BeautifulSoup

from database.connection import get_conn
from database.repos.leads_repo import LeadsRepo
from enrichisseur.mentions_legales_enricher import _trouver_ml_playwright_sync, _normalize_url, _clean_legal_text

_ML_KEYWORDS = ["mentions", "mention", "legales", "legale", "legal", "legal notice"]
_ML_FALLBACK_PATHS = ["/mentions-legales/", "/mentions-légales/", "/mentions-legales", "/mentions-légales", "/legal/", "/cgv/"]


def _trouver_ml_requests(base_url: str) -> Optional[str]:
    """Trouve et retourne le texte de la page ML via requests, ou None."""
    try:
        r = requests.get(
            base_url,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            allow_redirects=True,
        )
        if r.status_code != 200 or len(r.text) < 200:
            return None

        # Anti-bot check
        if "check" in r.text.lower() and ("browser" in r.text.lower() or "cloudflare" in r.text.lower() or "humain" in r.text.lower()):
            return None

        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            tag.decompose()

        # Try to find ML link on homepage
        ml_url = None
        for a in soup.find_all("a"):
            txt = (a.get_text() or "").lower().strip()
            href = (a.get("href") or "").lower()
            if any(k in txt or k in href for k in _ML_KEYWORDS):
                ml_url = a.get("href")
                break

        # Fallback: try direct paths
        if not ml_url:
            for path in _ML_FALLBACK_PATHS:
                target = urljoin(base_url, path)
                try:
                    r2 = requests.get(
                        target, timeout=8,
                        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                        allow_redirects=True,
                    )
                    if r2.status_code == 200 and len(r2.text) > 200:
                        title_lower = (BeautifulSoup(r2.text, "html.parser").title or "").lower()
                        if any(k in title_lower for k in ["404", "not found", "page introuvable"]):
                            continue
                        soup2 = BeautifulSoup(r2.text, "html.parser")
                        for tag in soup2(["script", "style", "nav", "footer", "header", "noscript"]):
                            tag.decompose()
                        text = soup2.get_text(separator=" ", strip=True)
                        if len(text) >= 100:
                            return text
                except Exception:
                    continue
            return None

        # Follow ML link
        if ml_url.startswith("http"):
            target = ml_url
        else:
            target = urljoin(base_url, ml_url)

        r2 = requests.get(
            target, timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            allow_redirects=True,
        )
        if r2.status_code != 200 or len(r2.text) < 100:
            return None

        soup2 = BeautifulSoup(r2.text, "html.parser")
        for tag in soup2(["script", "style", "nav", "footer", "header", "noscript"]):
            tag.decompose()
        return soup2.get_text(separator=" ", strip=True)

    except Exception:
        return None


def extraire_responsables_ml(site_web: str) -> str | None:
    """Retourne les 500 premiers mots de la page ML, ou None.
       Essai requests d'abord, fallback Playwright."""
    base_url = _normalize_url(site_web)
    if not base_url:
        return None

    # Tier 1: requests (rapide, fonctionne pour sites sans JS)
    text = _trouver_ml_requests(base_url)
    if text:
        text = _clean_legal_text(text)
        mots = text.split()
        if len(mots) > 500:
            mots = mots[:500]
        resultat = " ".join(mots)
        if len(resultat) >= 50:
            return resultat

    # Tier 2: Playwright (fallback pour sites avec JS/Cloudflare que requests ne passe pas)
    ml = _trouver_ml_playwright_sync(base_url)
    if not ml["text"]:
        return None

    text = _clean_legal_text(ml["text"])
    mots = text.split()
    if len(mots) > 500:
        mots = mots[:500]
    resultat = " ".join(mots)
    return resultat if len(resultat) >= 50 else None


_SKIP_DOMAINS = ["doctolib.fr", "planity.com", "maiia.com"]


def _is_skip_url(url: str) -> bool:
    """Ignore les URLs de plateformes de réservation sans mentions légales pro."""
    for d in _SKIP_DOMAINS:
        if d in url.lower():
            return True
    return False


def get_leads_a_traiter(limit: int | None = None, secteurs: list[str] | None = None) -> list[dict]:
    """Retourne les leads eligibles : site_web + ml_extracted vide (+ secteur optionnel)."""
    with get_conn() as conn:
        sql = """
            SELECT id, nom, site_web, secteur
            FROM leads_bruts
            WHERE site_web IS NOT NULL AND site_web != ''
              AND (ml_extracted IS NULL OR ml_extracted = '' OR ml_extracted = '{}')
        """
        params = []
        if secteurs:
            placeholders = ",".join("?" for _ in secteurs)
            sql += f" AND secteur IN ({placeholders})"
            params.extend(secteurs)
        sql += " ORDER BY id"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        leads = [dict(r) for r in rows]
        # Filtrer les URLs de plateformes (Doctolib, Planity, etc.)
        filtered = [l for l in leads if not _is_skip_url(l["site_web"])]
        skipped = len(leads) - len(filtered)
        if skipped:
            print(f"   [FILTRE] {skipped} leads ignores (plateformes reservation)")
        return filtered


def main(limit: int | None = None, secteurs: list[str] | None = None):
    leads = get_leads_a_traiter(limit, secteurs)
    total = len(leads)
    if total == 0:
        print("Aucun lead a traiter (ml_extracted deja rempli ou pas de site web).")
        return

    print(f"[...] {total} leads a traiter\n")
    ok = 0
    skip = 0

    repo = LeadsRepo()

    for i, lead in enumerate(leads, 1):
        lid = lead["id"]
        nom = lead["nom"] or "(sans nom)"
        secteur = lead.get("secteur", "")
        url = lead["site_web"]
        print(f"  [{i}/{total}] #{lid} [{secteur}] {nom[:40]:40s} {url}", end="")

        result = extraire_responsables_ml(url)
        if result:
            repo.update_fields(lid, {"ml_extracted": json.dumps({"raw_text": result}, ensure_ascii=False)})
            n_mots = len(result.split())
            print(f" -> OK ({n_mots} mots)")
            ok += 1
        else:
            repo.update_fields(lid, {"ml_extracted": json.dumps({"raw_text": None}, ensure_ascii=False)})
            print(f" -> RIEN (marque dans ml_extracted)")
            skip += 1

    print(f"\n{'='*50}")
    print(f"OK: {ok} | Rien: {skip} | Total: {total}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Extraction raw text des mentions legales")
    parser.add_argument("--test", type=int, default=None, help="Nombre de leads a traiter")
    parser.add_argument("--secteurs", nargs="+", default=None, help="Secteurs a filtrer (ex: cliniques_esthetiques ecoles_formation)")
    args = parser.parse_args()
    main(limit=args.test, secteurs=args.secteurs)
