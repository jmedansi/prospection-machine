# -*- coding: utf-8 -*-
"""
enrichisseur/update_ml_contacts.py

Met à jour email_2 et telephone_2 avec les emails/téléphones
extraits des mentions légales (ml_extracted) quand ils diffèrent
des valeurs déjà présentes dans email / telephone.

Overwrite aussi email si la valeur existante est un placeholder.
"""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore

from database.connection import get_conn
from database.repos.leads_repo import LeadsRepo

_PLACEHOLDER_RE = re.compile(
    r"@2x\.png|@3x\.png|@1x\.png"
    r"|@domain\.com|@email\.com|@yoursite|@domaine"
    r"|^utilisateur@|^votre@|^example@|^test@|^demo@"
    r"|^nom@|^prenom@|^contact@domaine"
    r"|^null@|^undefined@"
)


def _is_placeholder(email: str) -> bool:
    return bool(_PLACEHOLDER_RE.search(email.lower()))


def main(limit: int | None = None):
    with get_conn() as conn:
        sql = """
            SELECT id, nom, email, telephone, email_2, telephone_2, ml_extracted
            FROM leads_bruts
            WHERE ml_extracted IS NOT NULL AND ml_extracted != ''
              AND ml_extracted != '{}'
            ORDER BY id
        """
        if limit:
            sql += " LIMIT ?"
            rows = conn.execute(sql, (limit,)).fetchall()
        else:
            rows = conn.execute(sql).fetchall()

    total = len(rows)
    if total == 0:
        print("Aucun lead avec ml_extracted.")
        return

    repo = LeadsRepo()
    updated_email = 0
    updated_email2 = 0
    updated_tel2 = 0
    skipped = 0

    for i, row in enumerate(rows, 1):
        lid = row["id"]
        nom = (row["nom"] or "(sans nom)")[:40]
        data = json.loads(row["ml_extracted"])
        ml_emails = data.get("emails", [])
        ml_phones = data.get("phones", [])
        db_email = row["email"] or ""
        db_phone = row["telephone"] or ""
        db_email2 = row["email_2"] or ""
        db_phone2 = row["telephone_2"] or ""

        updates = {}

        # --- Email ---
        if ml_emails:
            first_ml = ml_emails[0]
            if _is_placeholder(db_email) and first_ml != db_email:
                # Overwrite with ML email, push old to email_2
                updates["email"] = first_ml
                if db_email:
                    updates["email_2"] = db_email
                updated_email += 1
            elif first_ml != db_email and first_ml not in db_email2:
                # Store in email_2
                existing = [e.strip() for e in db_email2.split(",") if e.strip()]
                if first_ml not in existing:
                    existing.append(first_ml)
                    updates["email_2"] = ", ".join(existing)
                    updated_email2 += 1
            # Also store additional ML emails in email_2
            extra = [e for e in ml_emails[1:] if e != db_email and e not in db_email2]
            if extra:
                existing = [e.strip() for e in (updates.get("email_2") or db_email2).split(",") if e.strip()]
                new_ones = [e for e in extra if e not in existing]
                if new_ones:
                    existing.extend(new_ones)
                    updates["email_2"] = ", ".join(existing)
                    updated_email2 += len(new_ones)

        # --- Phone ---
        if ml_phones:
            extra_phones = [p for p in ml_phones if p != db_phone and p not in db_phone2]
            if extra_phones:
                existing = [p.strip() for p in db_phone2.split(",") if p.strip()]
                new_ones = [p for p in extra_phones if p not in existing]
                if new_ones:
                    existing.extend(new_ones)
                    updates["telephone_2"] = ", ".join(existing)
                    updated_tel2 += len(new_ones)

        # Preserve existing email_2 / telephone_2 values
        append_keys = {"email_2", "telephone_2"}
        for k in append_keys:
            if k in updates:
                current = row[k] or ""
                updates[k] = updates[k]

        if updates:
            repo.update_fields(lid, updates)
            ok_parts = []
            if "email" in updates:
                ok_parts.append(f"email→{updates['email']}")
            if "email_2" in updates:
                ok_parts.append(f"email_2+")
            if "telephone_2" in updates:
                ok_parts.append(f"tel_2+")
            print(f"  [{i}/{total}] #{lid} {nom:40s} -> {' | '.join(ok_parts)}")
        else:
            skipped += 1

    print(f"\n{'='*50}")
    print(f"Email overwritten (placeholder): {updated_email}")
    print(f"Email_2 enriched: {updated_email2}")
    print(f"Telephone_2 enriched: {updated_tel2}")
    print(f"Skipped (no changes): {skipped}")
    print(f"Total: {total}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", type=int, default=None)
    args = parser.parse_args()
    main(limit=args.test)
