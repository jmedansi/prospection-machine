# -*- coding: utf-8 -*-
"""
enrichisseur/structure_ml_notes.py

Lit le texte brut des mentions légales (leads_bruts.notes)
et extrait les informations structurées via regex :
  - Personnes (rôle, prénom, nom, email, téléphone associé)
  - Emails et téléphones seuls
  - SIRET/SIREN/RCS
  - Adresse physique
  - Éditeur / société
  - Capital social

Stocke le résultat en JSON dans leads_bruts.ml_extracted,
et remplit nom_gerant/prenom_gerant/email/téléphone si vides.
"""

import json
import os
import re
import sys

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from database.connection import get_conn
from database.repos.leads_repo import LeadsRepo

# ─── Character helpers ────────────────────────────────────────────────────

_EE = chr(0xe9)
_CC = chr(0xc9)
_AN = "A-Za-z" + chr(0xc0) + "-" + chr(0xd6) + chr(0xd8) + "-" + chr(0xf6) + chr(0xf8) + "-" + chr(0xff)

# ─── Shared role / name fragments ──────────────────────────────────────────

_ROLE_FRAGMENT = (
    r"G(?:" + _EE + r"|e)rant"
    r"|Directeur\s+(?:g(?:"
    + _EE + r"|e)n(?:"
    + _EE + r"|e)ral\s+)?(?:(?:de\s+(?:la\s+)?)?(?:publication|r(?:"
    + _EE + r"|e)daction)|du\s+site)?"
    r"|Responsable\s+(?:(?:de\s+(?:la\s+)?)?(?:publication|(?:"
    + _EE + r"|e)dition|r(?:"
    + _EE + r"|e)daction)|du\s+site|(?:"
    + _EE + r"|e)ditorial)"
    r"|(?:"
    + _CC + r"|E)diteur"
    + r"|Propri(?:"
    + _EE + r"|e)taire"
    + r"|Cr(?:"
    + _EE + r"|e)ateur|Webmaster"
    + r"|Pr(?:"
    + _EE + r"|e)sident|Fondateur|Co[-\s]?fondateur|CEO|PDG|DG|Administrateur"
)

_NAME_FRAGMENT = r"(?P<nom_complet>[" + _AN + r"]+(?:[\s-][" + _AN + r"]+)+?)"

# ─── Person patterns ──────────────────────────────────────────────────────

_SEP = "•\u2013\u2014"  # bullet, en-dash, em-dash
_PHONE_PATTERN = r"(?:(?:\+|00)33[\s.\-]?(?:\(0\)[\s.\-]?)?|0)[1-9](?:[\s.\-]?\d{2}){4}"

# Pattern A: "Role : Name • email • phone"
_PERSON_LINE_RE = re.compile(
    r"(?P<role>" + _ROLE_FRAGMENT + r")"
    r"\s*[:;\u2013\u2014-]?\s*"
    r"(?:(?:M(?:me|lle|r)\.?|M\.)\s+)?"
    + _NAME_FRAGMENT
    + r"(?:\s*[" + _SEP + r"\s]\s*(?P<email>[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}))?"
    r"(?:\s*[" + _SEP + r"\s]\s*(?P<phone>" + _PHONE_PATTERN + r"))?"
)

# Pattern B: "M./Mme Name en sa qualité de Role" (role after name)
_PERSON_QUALITE_RE = re.compile(
    r"(?:M(?:me|lle|r)\.?(?:\s*/\s*M(?:me|lle|r)\.?)?\s+)?"
    + _NAME_FRAGMENT
    + r"\s+en\s+sa\s+qualit(?:"
    + _EE + r"|e)\s+de\s+"
    r"(?P<role>"
    r"G(?:"
    + _EE + r"|e)rant"
    + r"|Directeur(?:\s+g(?:"
    + _EE + r"|e)n(?:"
    + _EE + r"|e)ral)?"
    + r"|Pr(?:"
    + _EE + r"|e)sident"
    + r"|Responsable"
    + r")",
    re.IGNORECASE
)

# Pattern C: "M. Name, rôle" (narrative style)
_PERSON_NARRATIVE_RE = re.compile(
    r"(?:M(?:me|lle|r)\.?\s+)?"
    r"(?P<role>"
    r"G(?:"
    + _EE + r"|e)rant"
    + r"|Directeur(?:\s+g(?:"
    + _EE + r"|e)n(?:"
    + _EE + r"|e)ral)?"
    + r"|Pr(?:"
    + _EE + r"|e)sident"
    + r"|Fondateur|CEO"
    + r")\s+(?:est\s+)?"
    r"(?:(?:M(?:me|lle|r)\.?\s+)?)"
    + _NAME_FRAGMENT,
    re.IGNORECASE
)

# ─── Simple extraction patterns ───────────────────────────────────────────

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

PHONE_RE = re.compile(_PHONE_PATTERN)

SIRET_RE = re.compile(r"\b(\d{3,4}[\s-]?\d{3}[\s-]?\d{3}[\s-]?\d{5})\b")

RCS_RE = re.compile(
    r"RCS\s*(?:de\s+)?([A-Za-z\s]+?)?\s*:?\s*(\d{3}[\s-]?\d{3}[\s-]?\d{3})",
    re.IGNORECASE
)

CAPITAL_RE = re.compile(
    r"(?:capital\s+(?:social\s+)?(?:de\s+)?|Capital\s+)([\d\s]+)\s*(?:€|euros|EUR)",
    re.IGNORECASE
)

ADDRESS_RE = re.compile(
    r"(\d+)\s*(?:bis|ter|quater)?\s*"
    r"(?:rue|boulevard|bd|avenue|av|place|impasse|chemin|cours|all(?:é|e)e|passage|square|route|quai|faubourg|passage|villa|cit(?:é|e)|domaine|lotissement|hameau|r(?:é|e)sidence|zone|za|zac|lieu[- ]?dit|sentier|promenade|esplanade|voie|angle|lots?\s*\d+)\s+"
    r"[" + _AN + r"0-9\s\-\'\.]+?"
    r"(\d{5})\s*[" + _AN + r"\s\-\']+",
    re.IGNORECASE
)

EDITOR_RE = re.compile(
    r"(?:(?:(?:[ÉE]|Ed)diteur|editeur)\s+(?:du\s+site|de\s+la\s+publication)?\s*[:;]?\s*"
    r"|propri(?:é|e)t(?:é|e)\s+exclusive\s+(?:du\s+site\s+)?(?:est\s+)?(?:la\s+)?(?:propri(?:é|e)t(?:é|e)\s+)?(?:de\s+)?)",
    re.IGNORECASE
)

# ─── Stop / skip words ────────────────────────────────────────────────────

_SKIP_WORDS = {
    "exemple", "example", "test", "demo", "votrenom", "votresite",
    "votresociete", "votreentreprise", "nom", "prenom",
    "directeur", "gerant", "responsable", "president",
    "fondateur", "ceo", "pdg", "societe", "entreprise",
    "site", "publication", "fonction", "hebergeur", "hébergeur",
    "orange", "centralapp", "webmaster",
}

_STOP_WORDS = {"a", "à", "sas", "sarl", "sas", "eurl", "sa", "sci", "ea",
               "siren", "siret", "rcs", "tva", "capital", "siege",
               "immatricule", "code", "ape", "naf", "tel", "email",
               "contact", "société", "societe", "entreprise",
               "le", "la", "les", "l", "d", "n", "s", "au", "aux", "et",
               "est", "sur", "sous", "pour", "par", "avec", "dans",
               "de", "du", "des"}

_CIVILITE_WORDS = {"monsieur", "madame", "mademoiselle", "mlle", "mme", "mr", "dr", "docteur"}


# ─── Person name splitting ────────────────────────────────────────────────

_TEMPLATE_WORDS = {"nom", "prenom", "prénom", "fonction", "societe", "société",
                    "adresse", "telephone", "email", "custom_text", "siege", "siège"}

def _split_name(full_name: str):
    """Sépare un nom complet en (prenom, nom). Permet les noms à 1 mot."""
    words = full_name.strip().strip(".,;:!?").split()
    if not words:
        return None, None
    # Reject if any word is a template placeholder
    for w in words:
        wc = w.strip(".,;:!?()[]").lower()
        if wc in _TEMPLATE_WORDS:
            return None, None
    clean = []
    for w in words:
        wc = w.strip(".,;:!?()[]").lower()
        if wc in _STOP_WORDS:
            break
        if wc in _CIVILITE_WORDS:
            continue
        clean.append(w.strip(".,;:!?()[]"))
    if not clean:
        return None, None
    if len(clean) == 1:
        n = clean[0].upper()
        if n.lower() in _SKIP_WORDS or n.lower() in _STOP_WORDS or len(n) <= 2:
            return None, None
        return None, n
    if len(clean) > 4:
        # Too many words — probably not a person name
        return None, None
    if clean[-1].isupper() or clean[-1][0].isupper():
        p = " ".join(clean[:-1])
        n = clean[-1]
    else:
        p = clean[0]
        n = " ".join(clean[1:])
    p = p.strip().capitalize() if " " not in p else " ".join(w.capitalize() for w in p.split())
    n = n.strip().upper()
    if p.lower() in _SKIP_WORDS or n.lower() in _SKIP_WORDS:
        return None, None
    if p.lower() in _STOP_WORDS or n.lower() in _STOP_WORDS:
        return None, None
    return p, n


# ─── Extraction functions ─────────────────────────────────────────────────

def _extract_persons(text: str) -> list[dict]:
    """Extrait toutes les personnes avec rôle, email et téléphone associés."""
    seen = set()
    persons = []

    _COMPANY_WORDS = {"sa", "sas", "sarl", "eurl", "sci", "ea", "snc",
                       "gmbh", "ltd", "inc", "llc", "corp", "centralapp",
                       "holding", "photographie", "photography"}

    def _add(p, role, email=None, phone=None):
        prenom, nom = _split_name(p)
        if not nom:
            return
        # Reject company names (all words are company suffixes or long all-caps)
        words = p.lower().split()
        company_word_count = sum(1 for w in words if w.strip(".,;:!?()") in _COMPANY_WORDS)
        if company_word_count == len(words):
            return
        if len(words) >= 3 and all(w.isupper() for w in words if w.isalpha()):
            return
        key = f"{prenom or ''}|{nom}|{role}"
        if key in seen:
            return
        seen.add(key)
        persons.append({
            "role": role.strip().capitalize(),
            "prenom": prenom or "",
            "nom": nom,
            "email": email or "",
            "telephone": phone or "",
        })

    # Pattern A: "Role : Name • email • phone"
    for m in _PERSON_LINE_RE.finditer(text):
        role = m.group("role").strip()
        name = m.group("nom_complet").strip()
        email = m.group("email")
        phone = m.group("phone")
        phone = re.sub(r"[\s.\-]", "", phone) if phone else None
        _add(name, role, email, phone)

    # Pattern B: "Name en sa qualité de Role"
    for m in _PERSON_QUALITE_RE.finditer(text):
        role = m.group("role").strip()
        name = m.group("nom_complet").strip()
        # Chercher email/phone à proximité (50 chars after match)
        end = m.end()
        nearby = text[end:end + 100]
        email_m = EMAIL_RE.search(nearby)
        phone_m = PHONE_RE.search(nearby)
        email = email_m.group(0) if email_m else None
        phone = re.sub(r"[\s.\-]", "", phone_m.group(0)) if phone_m else None
        _add(name, role, email, phone)

    # Pattern C: narrative "Role Name"
    for m in _PERSON_NARRATIVE_RE.finditer(text):
        role = m.group("role").strip()
        name = m.group("nom_complet").strip()
        end = m.end()
        nearby = text[end:end + 100]
        email_m = EMAIL_RE.search(nearby)
        phone_m = PHONE_RE.search(nearby)
        email = email_m.group(0) if email_m else None
        phone = re.sub(r"[\s.\-]", "", phone_m.group(0)) if phone_m else None
        _add(name, role, email, phone)

    return persons


def _extract_emails(text: str) -> list[str]:
    """Extrait tous les emails uniques."""
    seen = set()
    emails = []
    for m in EMAIL_RE.finditer(text):
        e = m.group(0).strip().lower()
        if any(skip in e for skip in ["example.com", "domain.com", "yoursite", "votre"]):
            continue
        if e not in seen:
            seen.add(e)
            emails.append(e)
    return emails


def _extract_phones(text: str) -> list[str]:
    """Extrait et normalise tous les téléphones uniques."""
    seen = set()
    phones = []
    for m in PHONE_RE.finditer(text):
        p = re.sub(r"[\s.\-]", "", m.group(0))
        if p.startswith("+33"):
            p = "0" + p[3:]
        elif p.startswith("0033"):
            p = "0" + p[4:]
        if p not in seen and len(p) == 10:
            seen.add(p)
            phones.append(p)
    return phones


def _extract_siret(text: str) -> str | None:
    """Extrait le numéro SIRET (14 chiffres) ou SIREN (9 chiffres)."""
    for m in SIRET_RE.finditer(text):
        siret = re.sub(r"[\s-]", "", m.group(1))
        if len(siret) == 14:
            return siret
    # Fallback: 14 digits consecutive
    m = re.search(r"\b(\d{14})\b", text)
    if m:
        return m.group(1)
    return None


def _extract_rcs(text: str) -> str | None:
    """Extrait le numéro RCS."""
    for m in RCS_RE.finditer(text):
        num = re.sub(r"[\s-]", "", m.group(2))
        return f"RCS {m.group(1) or ''} {num}".strip()
    # Fallback: generic RCS pattern
    m = re.search(r"RCS\s*:?\s*(\d{3}\s?\d{3}\s?\d{3})", text, re.IGNORECASE)
    if m:
        return f"RCS {re.sub(r'\s', '', m.group(1))}"
    return None


def _extract_capital(text: str) -> str | None:
    """Extrait le capital social."""
    m = CAPITAL_RE.search(text)
    if m:
        amount = " ".join(m.group(1).split())
        return f"{amount} €"
    return None


def _extract_address(text: str) -> str | None:
    """Extrait une adresse physique."""
    for m in ADDRESS_RE.finditer(text):
        addr = m.group(0).strip()
        if len(addr) > 15 and len(addr) < 200:
            return addr
    return None


def _extract_editor(text: str) -> str | None:
    """Extrait le nom de l'éditeur / société propriétaire."""
    # Try "Editeur : Name" first
    parts = EDITOR_RE.split(text, maxsplit=1)
    if len(parts) > 1:
        after = parts[1].strip()
        # Take up to first period, newline, or common breakers
        editor = after.split(".")[0].split("\n")[0].strip()
        editor = re.sub(r"\s+", " ", editor)
        # Cut at known stop points
        for stop in ["au capital", "siret", "rcs", "tva", "siège", "email", "tel"]:
            idx = editor.lower().find(stop)
            if idx > 10:
                editor = editor[:idx].strip()
        if 3 < len(editor) < 150:
            return editor
    return None


def structure_ml_notes(text: str) -> dict:
    """Analyse le texte brut d'une page ML et retourne un dict structuré."""
    result = {
        "persons": [],
        "emails": [],
        "phones": [],
        "siret": None,
        "rcs": None,
        "capital": None,
        "adresse": None,
        "editeur": None,
    }

    if not text or len(text.strip()) < 20:
        return result

    result["persons"] = _extract_persons(text)
    result["emails"] = _extract_emails(text)
    result["phones"] = _extract_phones(text)
    result["siret"] = _extract_siret(text)
    result["rcs"] = _extract_rcs(text)
    result["capital"] = _extract_capital(text)
    result["adresse"] = _extract_address(text)
    result["editeur"] = _extract_editor(text)

    return result


# ─── Main ─────────────────────────────────────────────────────────────────

def main(limit: int | None = None):
    """Parcourt les leads avec notes et structure les données ML."""
    with get_conn() as conn:
        sql = """
            SELECT id, nom, site_web, notes, email, telephone, adresse,
                   nom_gerant, prenom_gerant
            FROM leads_bruts
            WHERE notes IS NOT NULL AND notes != ''
              AND (ml_extracted IS NULL OR ml_extracted = '')
            ORDER BY id
        """
        if limit:
            sql += " LIMIT ?"
            rows = conn.execute(sql, (limit,) if limit else ()).fetchall()
        else:
            rows = conn.execute(sql).fetchall()

    total = len(rows)
    if total == 0:
        print("Aucun lead à traiter (notes vides ou déjà structurées).")
        return

    print(f"[...] {total} leads à structurer\n")

    repo = LeadsRepo()
    ok = 0
    empty_notes = 0

    for i, row in enumerate(rows, 1):
        lead = dict(row)
        lid = lead["id"]
        nom = lead["nom"] or "(sans nom)"
        notes = lead["notes"]
        url = lead["site_web"] or ""

        safe_nom = nom[:40].encode("utf-8", errors="replace").decode("utf-8", errors="replace")
        print(f"  [{i}/{total}] #{lid} {safe_nom:40s}", end="")

        struct = structure_ml_notes(notes)

        if struct["persons"] or struct["emails"] or struct["phones"] or struct["siret"]:
            # Save JSON to ml_extracted
            repo.update_fields(lid, {"ml_extracted": json.dumps(struct, ensure_ascii=False)})

            # Update simple fields if empty
            updates = {}

            # First person is usually the main manager
            if struct["persons"]:
                p = struct["persons"][0]
                if not lead["prenom_gerant"] and not lead["nom_gerant"]:
                    updates["prenom_gerant"] = p["prenom"]
                    updates["nom_gerant"] = p["nom"]

            # First email if empty
            if not lead["email"] and struct["emails"]:
                # Prefer an email associated with a person
                person_emails = [p["email"] for p in struct["persons"] if p.get("email")]
                best_email = person_emails[0] if person_emails else struct["emails"][0]
                updates["email"] = best_email

            # First phone if empty
            if not lead["telephone"] and struct["phones"]:
                updates["telephone"] = struct["phones"][0]

            # Address if empty
            if not lead["adresse"] and struct["adresse"]:
                updates["adresse"] = struct["adresse"]

            if updates:
                repo.update_fields(lid, updates)

            details = f"{len(struct['persons'])} pers, {len(struct['emails'])} email, {len(struct['phones'])} tel"
            print(f" -> OK ({details})")
            ok += 1
        else:
            print(" -> RIEN (texte non structure)")
            # Mark as processed even if empty
            repo.update_fields(lid, {"ml_extracted": json.dumps(struct, ensure_ascii=False)})
            empty_notes += 1

    print(f"\n{'='*50}")
    print(f"OK: {ok} | Vides: {empty_notes} | Total: {total}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Structure les notes ML en JSON")
    parser.add_argument("--test", type=int, default=None, help="Nombre de leads à traiter")
    args = parser.parse_args()
    main(limit=args.test)
