# -*- coding: utf-8 -*-
"""
enrichisseur/extract_responsables_ml.py

Pipeline :
  leads_bruts (notes vide, site_web non vide)
    → Playwright : homepage → lien ML → 500 premiers mots
    → stocke dans leads_bruts.notes
"""

import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from database.connection import get_conn
from database.repos.leads_repo import LeadsRepo
from enrichisseur.mentions_legales_enricher import _trouver_ml_playwright_sync, _normalize_url, _clean_legal_text


def extraire_responsables_ml(site_web: str) -> str | None:
    """Retourne les 200 premiers mots de la page ML, ou None."""
    base_url = _normalize_url(site_web)
    if not base_url:
        return None

    ml = _trouver_ml_playwright_sync(base_url)
    if not ml["text"]:
        return None

    text = _clean_legal_text(ml["text"])
    mots = text.split()
    if len(mots) > 500:
        mots = mots[:500]
    resultat = " ".join(mots)
    return resultat if len(resultat) >= 50 else None


def get_leads_a_traiter(limit: int | None = None) -> list[dict]:
    """Retourne les leads eligibles : site_web + notes vide."""
    with get_conn() as conn:
        sql = """
            SELECT id, nom, site_web
            FROM leads_bruts
            WHERE site_web IS NOT NULL AND site_web != ''
              AND (notes IS NULL OR notes = '')
            ORDER BY id
        """
        if limit:
            sql += " LIMIT ?"
            rows = conn.execute(sql, (limit,)).fetchall()
        else:
            rows = conn.execute(sql).fetchall()
        return [dict(r) for r in rows]


def main(limit: int | None = None):
    leads = get_leads_a_traiter(limit)
    total = len(leads)
    if total == 0:
        print("Aucun lead a traiter (notes deja remplies ou pas de site web).")
        return

    print(f"[...] {total} leads a traiter\n")
    ok = 0
    skip = 0

    repo = LeadsRepo()

    for i, lead in enumerate(leads, 1):
        lid = lead["id"]
        nom = lead["nom"] or "(sans nom)"
        url = lead["site_web"]
        print(f"  [{i}/{total}] #{lid} {nom[:40]:40s} {url}", end="")

        result = extraire_responsables_ml(url)
        if result:
            repo.update_fields(lid, {"notes": result})
            print(f" -> OK:")
            for line in result.split("\n"):
                line = line.strip()
                if line:
                    print(f"       {line}")
            ok += 1
        else:
            # Ne pas ecrire de placeholder — laisser notes vide
            print(f" -> RIEN (notes laissee vide)")
            skip += 1

    print(f"\n{'='*50}")
    print(f"OK: {ok} | Rien: {skip} | Total: {total}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Extraction des responsables via ML + LLM")
    parser.add_argument("--test", type=int, default=None, help="Nombre de leads a traiter (test)")
    args = parser.parse_args()
    main(limit=args.test)
