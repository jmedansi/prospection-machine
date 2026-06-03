# -*- coding: utf-8 -*-
"""
enrichisseur/mentions_legales_enricher.py

Scrape la page "mentions légales" des sites web des leads et extrait :
  - Nom du dirigeant / responsable de publication / gérant
  - Email(s) de contact
  - Numéro(s) de téléphone

Stocke le résultat dans leads_bruts.notes + met à jour les champs dédiés.

Filtres :
  - source='ads'             → tous
  - source='maps'            → nb_avis > 50
  - notes vide               → pas déjà traité
"""

import asyncio
import json
import re
import sys
import os
from urllib.parse import urljoin

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from database.connection import get_conn
from database.repos.leads_repo import LeadsRepo
from config_manager import handle_llm_call

# ─── Regex ─────────────────────────────────────────────────────────────────────

_EE = chr(0xe9)
_CC = chr(0xc9)
_AN = "A-Za-z" + chr(0xc0) + "-" + chr(0xd6) + chr(0xd8) + "-" + chr(0xf6) + chr(0xf8) + "-" + chr(0xff)

_TITRE_RE = re.compile(
    ("(?:"
     "G(?:" + _EE + "|e)rant|Directeur\\s+(?:g(?:" + _EE + "|e)n(?:" + _EE + "|e)ral\\s+)?"
     "(?:(?:de\\s+la\\s+)?(?:publication|r(?:" + _EE + "|e)daction)|du\\s+site)?"
     "|Responsable\\s+(?:"
     "(?:de\\s+la\\s+)?(?:publication|(?:" + _EE + "|e)dition|r(?:" + _EE + "|e)daction)"
     "|du\\s+site|(?:" + _EE + "|e)ditorial"
     ")"
     "|(?:" + _CC + "|E)diteur|Propri(?:" + _EE + "|e)taire|Cr(?:" + _EE + "|e)ateur|Webmaster"
     "|Pr(?:" + _EE + "|e)sident|Fondateur|Co[- ]?fondateur|CEO|PDG|DG"
     ")")
)

_NAME_AFTER_TITRE_RE = re.compile(
    ("(?:"
     "G(?:" + _EE + "|e)rant|Directeur\\s+(?:g(?:" + _EE + "|e)n(?:" + _EE + "|e)ral\\s+)?"
     "(?:(?:de\\s+la\\s+)?(?:publication|r(?:" + _EE + "|e)daction)|du\\s+site)?"
     "|Responsable\\s+(?:"
     "(?:de\\s+la\\s+)?(?:publication|(?:" + _EE + "|e)dition|r(?:" + _EE + "|e)daction)"
     "|du\\s+site|(?:" + _EE + "|e)ditorial"
     ")"
     "|(?:" + _CC + "|E)diteur|Propri(?:" + _EE + "|e)taire|Cr(?:" + _EE + "|e)ateur|Webmaster"
     "|Pr(?:" + _EE + "|e)sident|Fondateur|Co[- ]?fondateur|CEO|PDG|DG"
     ")"
     "\\s*[:;\\-]\\s*"
     "(?:(?:M(?:me|lle|r)\\.?|M\\.)\\s+)?"
     "([" + _AN + "]+(?:[\\s-][" + _AN + "]+(?:[\\s-][" + _AN + "]+)?)?)"),
    re.IGNORECASE
)

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

PHONE_RE = re.compile(
    r"(?:(?:\+|00)33[\s.\-]?(?:\(0\)[\s.\-]?)?|0)"
    r"[1-9](?:[\s.\-]?\d{2}){4}"
)

SIREN_RE = re.compile(r"\b(\d{3}\s?\d{3}\s?\d{3})\b")
TVA_RE = re.compile(r"(?:FR|fr)\s?\d{2}\s?\d{3}\s?\d{3}\s?\d{3}")

SKIP_WORDS = {
    "exemple", "example", "test", "demo", "votrenom", "votresite",
    "votresociete", "votreentreprise", "nom", "prenom",
    "directeur", "gerant", "responsable", "president",
    "fondateur", "ceo", "pdg", "societe", "entreprise",
}

CIVILITE_WORDS = {"monsieur", "madame", "mademoiselle", "mlle", "mme", "mr", "dr", "docteur"}

_STOP_WORDS = {"a", "à", "sas", "sarl", "sas", "eurl", "sa", "sci", "ea",
               "siren", "siret", "rcs", "tva", "capital", "siege",
               "immatricule", "code", "ape", "naf", "tel", "email",
               "contact", "société", "societe", "entreprise",
               "le", "la", "les", "l", "d", "n", "s"}

_ML_KEYWORDS = ["mentions", "mention", "legales", "legale", "legal", "legal notice"]

async def _trouver_ml_playwright(base_url: str) -> dict:
    """Playwright: charge homepage, trouve lien ML, clique, retourne texte."""
    result = {"url": None, "text": None, "error": None}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled", "--ignore-certificate-errors"]
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            ignore_https_errors=True
        )
        page = await ctx.new_page()
        try:
            await page.goto(base_url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(3000)
            try:
                for sel in ['button:has-text("Accepter")', 'button:has-text("Tout accepter")',
                            '[id*="accept"]', '[class*="accept"] button']:
                    btn = await page.query_selector(sel)
                    if btn and await btn.is_visible():
                        await btn.click(force=True, timeout=3000)
                        await page.wait_for_timeout(1000)
                        break
            except: pass
            # Scroll to bottom to trigger lazy-loaded footers
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1500)
            found = None
            links = await page.evaluate("""
                () => {
                    const items = [];
                    document.querySelectorAll('a').forEach(a => {
                        const txt = (a.textContent || '').trim().toLowerCase().replace(/\\s+/g, ' ');
                        const href = (a.getAttribute('href') || '').toLowerCase();
                        items.push({text: txt.slice(0, 100), href: href.slice(0, 150)});
                    });
                    return items;
                }
            """)
            for link in links:
                txt, href = link["text"], link["href"]
                if any(k in txt or k in href for k in _ML_KEYWORDS):
                    found = link
                    break
            if not found:
                # Fallback: try direct /mentions-legales/ and /mentions-légales/
                for suffix in ["/mentions-legales/", "/mentions-légales/", "/mentions-legales", "/mentions-légales", "/legal/"]:
                    try:
                        target = urljoin(base_url, suffix)
                        await page.goto(target, wait_until="domcontentloaded", timeout=10000)
                        await page.wait_for_timeout(1500)
                        title = (await page.title()).lower()
                        text_len = len(await page.evaluate("() => document.body.innerText"))
                        if any(k in title for k in ["404", "not found", "page introuvable"]):
                            continue
                        if text_len < 100:
                            continue
                        result["url"] = page.url
                        result["error"] = None
                        text = await page.evaluate("() => document.body.innerText")
                        result["text"] = text
                        return result
                    except Exception:
                        continue
                result["error"] = "aucun lien ML"
            else:
                target = found["href"]
                if target.startswith("http"):
                    await page.goto(target, wait_until="domcontentloaded", timeout=15000)
                else:
                    await page.goto(urljoin(base_url, target), wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_timeout(2000)
                result["url"] = page.url
                text = await page.evaluate("""
                    () => {
                        const t = document.body.innerText;
                        return t;
                    }
                """)
                result["text"] = text
        except Exception as e:
            result["error"] = str(e)[:200]
        await browser.close()
    return result


def _trouver_ml_playwright_sync(base_url: str) -> dict:
    """Wrapper synchrone pour _trouver_ml_playwright."""
    try:
        return asyncio.run(_trouver_ml_playwright(base_url))
    except Exception as e:
        return {"url": None, "text": None, "error": str(e)[:200]}


def _normalize_url(url: str) -> str:
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")


def _fetch_page(url: str) -> str | None:
    """Télécharge une page et retourne son texte brut."""
    try:
        r = requests.get(
            url,
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            allow_redirects=True,
        )
        if r.status_code == 200 and len(r.text) > 100:
            soup = BeautifulSoup(r.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
                tag.decompose()
            return soup.get_text(separator=" ", strip=True)
    except Exception:
        pass
    return None


def _capitalize_name(name: str) -> str:
    """Capitalize first letter of each part, handling hyphens (Marie-Aude → Marie-Aude)."""
    return "-".join(p.capitalize() for p in name.split("-"))


def _extract_dirigeant(text: str) -> tuple[str | None, str | None]:
    """Extrait prénom et nom du dirigeant via regex."""
    for m in _NAME_AFTER_TITRE_RE.finditer(text):
        raw = m.group(1).strip()
        # Couper au premier mot-stop (ex: "EMMANUEL BENISTY à SAS" → "EMMANUEL BENISTY")
        words = raw.split()
        clean = []
        for w in words:
            w_clean = w.strip(".,;:!?").lower()
            if w_clean in _STOP_WORDS:
                break
            if w_clean in CIVILITE_WORDS:
                continue  # Skip Monsieur/Madame/etc.
            clean.append(w.strip(".,;:!?"))
        if len(clean) < 1:
            continue

        # Distribuer les mots en prénom(s) + nom
        full = " ".join(clean)
        if len(clean) == 1:
            # Un seul mot → probablement juste le nom
            n = clean[0].upper()
            if n.lower() not in SKIP_WORDS and len(n) > 1:
                return None, n
            continue
        elif len(clean) == 2:
            p, n = clean[0], clean[1]
        else:
            # 3+ mots: "Jean Pierre MARTIN" → prenom="Jean Pierre", nom="MARTIN"
            # ou "Marie-Aude ULVOAS" selon la casse
            # Si le dernier mot est en MAJUSCULES, c'est le nom
            if clean[-1].isupper() or clean[-1][0].isupper():
                p = " ".join(clean[:-1])
                n = clean[-1]
            else:
                p = clean[0]
                n = " ".join(clean[1:])

        # Capitalize properly (handle "Marie-Aude" -> "Marie-Aude", not "Marie-aude")
        p = _capitalize_name(p.strip())
        n = n.strip().upper()
        if p.lower() in SKIP_WORDS or n.lower() in SKIP_WORDS:
            continue
        if len(p) > 1 and len(n) > 1:
            return p, n

    return None, None


def _extract_dirigeant_llm(text: str) -> tuple[str | None, str | None]:
    """Extrait prenom et nom du dirigeant via GROQ (LLaMA 70B).
    Fallback silencieux vers regex si le LLM echoue."""
    try:
        # Trouver le bloc contenant le dirigeant : chercher les mots-cles
        keywords = ["responsable", "directeur", "gerant", "editeur", "publication", "hebergement"]
        best_start = 0
        for kw in keywords:
            idx = text.lower().find(kw)
            if idx >= 0 and (best_start == 0 or idx < best_start):
                best_start = idx
        # Envoyer 600 chars autour du mot-cle, ou les premiers 800 si rien trouve
        if best_start > 0:
            start = max(0, best_start - 100)
            snippet = text[start:start + 600]
        else:
            snippet = text[:800]
        prompt = (
            'Tu analyses une page de mentions legales. '
            'Extrais le nom du responsable de publication / directeur de publication / gerant. '
            'Retourne UNIQUEMENT du JSON valide sans formatage : '
            '{"prenom": "..." ou null, "nom": "..." ou null}. '
            'Texte : """' + snippet + '"""'
        )
        system = (
            "Tu es un assistant specialise dans l'extraction de donnees juridiques. "
            "Ne reponds qu'en JSON valide."
        )
        raw = handle_llm_call(prompt, system=system, model="llama-3.3-70b-versatile")
        # Nettoyer la reponse : enlever les markdown fences si presents
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        cleaned = cleaned.strip()
        data = json.loads(cleaned)
        prenom = data.get("prenom") or None
        nom = data.get("nom") or None
        if prenom and nom:
            p = str(prenom).strip()
            n = str(nom).strip().upper()
            if _est_nom_valide(p, n):
                return p, n
    except Exception:
        pass
    return None, None


def _est_nom_valide(prenom: str, nom: str) -> bool:
    """Filtre les noms absurdes produits par le LLM (faux positifs)."""
    full = (prenom + " " + nom).lower()
    if any(bad in full for bad in ["personne physique", "votre nom", "votre prenom",
                                    "example", "test", "demo", "inconnu", "unknown",
                                    "non specifie", "non precise", "null", "undefined"]):
        return False
    if prenom.lower() in _STOP_WORDS or nom.lower() in _STOP_WORDS:
        return False
    if len(prenom) <= 1 or len(nom) <= 1:
        return False
    if len(prenom) > 25 or len(nom) > 30:
        return False
    return True


def _extract_emails(text: str) -> list[str]:
    """Extrait les emails uniques."""
    seen = set()
    emails = []
    for m in EMAIL_RE.finditer(text):
        e = m.group(0).strip().lower()
        # Filtrer les emails génériques / faux
        if any(skip in e for skip in ["example.com", "domain.com", "yoursite", "votre"]):
            continue
        if e not in seen:
            seen.add(e)
            emails.append(e)
    return emails


def _extract_phones(text: str) -> list[str]:
    """Extrait et normalise les numéros de téléphone."""
    seen = set()
    phones = []
    for m in PHONE_RE.finditer(text):
        p = re.sub(r"[\s.\-]", "", m.group(0))
        # Normaliser +33 → 0
        if p.startswith("+33"):
            p = "0" + p[3:]
        elif p.startswith("0033"):
            p = "0" + p[4:]
        if p not in seen and len(p) == 10:
            seen.add(p)
            phones.append(p)
    return phones


def _clean_legal_text(text: str) -> str:
    """Nettoie le texte pour enlever les artefacts cookies/RGPD."""
    low = text.lower()
    if any(k in low for k in ["paramètres des cookies", "parametres des cookies"]):
        text = re.split(r"(?i)(?:paramètres|parametres)\s+des\s+cookies", text)[0]
    return text.strip()


def _parse_legal_text(result: dict, text: str):
    """Extract dirigeant via LLM, fallback regex, puis emails/phones regex."""
    prenom, nom = _extract_dirigeant_llm(text)
    if not prenom or not nom:
        prenom, nom = _extract_dirigeant(text)
    if prenom and nom:
        result["dirigeant_prenom"] = prenom
        result["dirigeant_nom"] = nom
    result["emails"] = _extract_emails(text)
    result["telephones"] = _extract_phones(text)


def enrichir_lead(lead_id: int, site_web: str, nom_entreprise: str) -> dict:
    """Scrape les mentions légales et retourne les infos trouvées.
    Utilise Playwright d'abord (JS-rendered), fallback requests."""
    result = {
        "dirigeant_prenom": None,
        "dirigeant_nom": None,
        "emails": [],
        "telephones": [],
        "url_trouvee": None,
    }

    base_url = _normalize_url(site_web)
    if not base_url:
        return result

    # 1. Playwright d'abord (gère JS, cookie banners, etc.)
    ml = _trouver_ml_playwright_sync(base_url)
    if ml["text"]:
        result["url_trouvee"] = ml["url"]
        text = _clean_legal_text(ml["text"])
        _parse_legal_text(result, text)
        return result

    # 2. Fallback requests (sites simples sans JS)
    try:
        r = requests.get(
            base_url, timeout=6,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            allow_redirects=True,
        )
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            ml_keywords = ["mention", "légale", "legale", "legal"]
            for a in soup.find_all("a", href=True):
                txt = (a.text or "").lower()
                href = a["href"].lower()
                if any(k in txt or k in href for k in ml_keywords):
                    full_url = urljoin(base_url, a["href"])
                    text = _fetch_page(full_url)
                    if text:
                        result["url_trouvee"] = full_url
                        text = _clean_legal_text(text)
                        _parse_legal_text(result, text)
                        break
    except Exception:
        pass

    return result


def _format_notes(result: dict) -> str:
    """Formate les infos pour le champ notes."""
    parts = []
    if result["dirigeant_prenom"] and result["dirigeant_nom"]:
        parts.append(f"Dirigeant: {result['dirigeant_prenom']} {result['dirigeant_nom']}")
    if result["emails"]:
        parts.append(f"Email: {', '.join(result['emails'])}")
    if result["telephones"]:
        parts.append(f"Tél: {', '.join(result['telephones'])}")
    if result["url_trouvee"]:
        parts.append(f"(ML: {result['url_trouvee']})")
    return " | ".join(parts) if parts else ""


def get_leads_a_enrichir(limit: int | None = None) -> list[dict]:
    """Retourne les leads éligibles : site web + filtres source + notes vide."""
    with get_conn() as conn:
        sql = """
            SELECT id, nom, site_web, source, nb_avis
            FROM leads_bruts
            WHERE site_web IS NOT NULL AND site_web != ''
              AND (notes IS NULL OR notes = '')
              AND (
                  (source = 'ads')
                  OR (source = 'maps' AND nb_avis > 50)
                  OR (source IS NULL)
              )
            ORDER BY id
        """
        if limit:
            sql += " LIMIT ?"
            rows = conn.execute(sql, (limit,)).fetchall()
        else:
            rows = conn.execute(sql).fetchall()
        return [dict(r) for r in rows]


def update_db(lead_id: int, notes: str, result: dict):
    """Met à jour notes + champs dédiés."""
    repo = LeadsRepo()
    # Met à jour notes dans leads_bruts + ceo_prenom/nom dans leads_audites
    update_data = {"notes": notes}
    if result["dirigeant_prenom"]:
        update_data["ceo_prenom"] = result["dirigeant_prenom"]
    if result["dirigeant_nom"]:
        update_data["ceo_nom"] = result["dirigeant_nom"]
    repo.update_fields(lead_id, update_data)

    # Met à jour telephone_sniper dans leads_audites (pas géré par update_fields)
    if result["telephones"]:
        try:
            with get_conn() as conn:
                audit = conn.execute(
                    "SELECT id FROM leads_audites WHERE lead_id=? ORDER BY id DESC LIMIT 1",
                    (lead_id,)
                ).fetchone()
                if audit:
                    tel = result["telephones"][0]
                    conn.execute(
                        "UPDATE leads_audites SET telephone_sniper=? WHERE id=?",
                        (tel, audit["id"])
                    )
                    conn.commit()
        except Exception:
            pass


def main(limit: int | None = None):
    """Point d'entrée principal."""
    leads = get_leads_a_enrichir(limit)
    total = len(leads)
    if total == 0:
        print("✅ Aucun lead à enrichir (notes déjà remplies ou pas de site web).")
        return

    print(f"[...] {total} leads a traiter\n")
    ok = 0
    skip = 0

    for i, lead in enumerate(leads, 1):
        lid = lead["id"]
        nom = lead["nom"] or "(sans nom)"
        url = lead["site_web"]
        print(f"  [{i}/{total}] {nom} — {url}", end="")

        result = enrichir_lead(lid, url, nom)

        notes = _format_notes(result)
        if notes:
            update_db(lid, notes, result)
            print(f" -> OK: {notes}")
            ok += 1
        else:
            update_db(lid, "(rien trouve sur mentions legales)", result)
            print(f" -> RIEN (page ML inaccessible ou vide)")
            skip += 1

    print(f"\n{'='*50}")
    print(f"OK: {ok} enrichis | Vides: {skip} | Total: {total}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Enrichit les leads depuis les mentions légales")
    parser.add_argument("--test", type=int, default=None, help="Nombre de leads à traiter (test)")
    args = parser.parse_args()
    main(limit=args.test)
