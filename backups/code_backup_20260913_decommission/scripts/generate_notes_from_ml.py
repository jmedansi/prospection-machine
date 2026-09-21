#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Génère des notes à appliquer depuis un dump ml_extracted JSONL.
Écrit deux fichiers:
 - notes_to_apply.jsonl  (id, notes)
 - ambiguous_ml.jsonl    (id, reason, ml_extracted)

Usage:
  python scripts/generate_notes_from_ml.py --in ml_extracted_dump.jsonl --out notes_to_apply.jsonl
"""
import json
import argparse
import re

VENDOR_KEYWORDS = [
    'waze.com', 'developer@', 'support@', 'privacy@', 'ionos', 'ovh', 'shopify',
    'agence@', 'agence', 'virtuosa', 'websideconseil', 'clararp.com', 'fraser-communications',
    'contentdesignlab.com', 'jungle-melody', 'joinoko', 'marcus@', '1chr.fr'
]

PRIORITY_ROLES = [
    'gérant', 'gerant', 'président', 'president', 'directeur général', 'directeur general',
    'directeur', 'directeur de la publication', 'directeur de publication', 'directeur de la publication',
    'responsable publication', 'responsable de publication', 'responsable de la publication',
    'propriétaire', 'proprietaire', 'editeur', 'éditeur', 'fondateur', 'ceo', 'pdg', 'dg'
]

VENDOR_ROLES = ['webmaster', 'web', 'agence', 'designer', 'hébergeur', 'hebergeur', 'prestataire', 'studio', 'créateur', 'creation']


def is_vendor_email(e: str) -> bool:
    if not e:
        return False
    el = e.lower()
    for k in VENDOR_KEYWORDS:
        if k in el:
            return True
    return False


def role_is_vendor(role: str) -> bool:
    if not role:
        return False
    rl = role.lower()
    for k in VENDOR_ROLES:
        if k in rl:
            return True
    return False


def role_priority_score(role: str) -> int:
    if not role:
        return 0
    rl = role.lower()
    for i, r in enumerate(PRIORITY_ROLES, 1):
        if r in rl:
            return len(PRIORITY_ROLES) - i + 10
    return 1


def choose_best_person(persons: list) -> dict | None:
    # Filter out vendor roles and names that look like agencies
    candidates = []
    for p in persons:
        role = p.get('role') or ''
        nom = (p.get('nom') or '')
        prenom = (p.get('prenom') or '')
        email = p.get('email') or ''
        # Skip if role indicates vendor
        if role_is_vendor(role):
            continue
        # Skip if name contains vendor keywords
        lower_name = f"{prenom} {nom}".lower()
        if any(k in lower_name for k in ['agence', 'studio', 'web', 'developer', 'dev', 'agency', 'virtuosa']):
            continue
        # Skip if email is vendor
        if is_vendor_email(email):
            email = ''
        score = role_priority_score(role)
        candidates.append((score, p))
    if not candidates:
        return None
    # Pick highest score, tie-breaker: has email
    candidates.sort(key=lambda x: (x[0], bool(x[1].get('email'))), reverse=True)
    return candidates[0][1]


def best_contact_from_ml(ml: dict) -> tuple[str, list]:
    # returns (note, warnings[])
    warnings = []
    persons = ml.get('persons') or []
    emails = [e for e in (ml.get('emails') or []) if not is_vendor_email(e)]
    phones = ml.get('phones') or []

    person = choose_best_person(persons)
    if person:
        name = ' '.join(filter(None, [person.get('prenom') or '', person.get('nom') or ''])).strip()
        if not name:
            # fallback to nom only
            name = person.get('nom') or ''
        parts = []
        if name:
            parts.append(f"Dirigeant: {name}")
        # prefer person email
        p_email = person.get('email') or ''
        if p_email and not is_vendor_email(p_email):
            parts.append(f"Email: {p_email}")
        elif emails:
            parts.append(f"Email: {emails[0]}")
        if person.get('telephone'):
            parts.append(f"Tel: {person.get('telephone')}")
        elif phones:
            parts.append(f"Tel: {phones[0]}")
        note = ' | '.join(parts)
        return note, warnings

    # No clear person -> use best email/phone for company
    if emails or phones:
        parts = []
        if emails:
            parts.append(f"Email: {emails[0]}")
        if phones:
            parts.append(f"Tel: {phones[0]}")
        note = ' | '.join(parts)
        return note, warnings

    # Only vendor contacts or nothing
    warnings.append('no_valid_contact_or_only_vendors')
    return '(rien trouve sur mentions legales)', warnings


def main(input_path, output_path, ambiguous_path):
    notes = []
    ambiguous = []
    with open(input_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            lid = obj.get('id')
            ml = obj.get('ml_extracted') or {}
            note, warnings = best_contact_from_ml(ml)
            notes.append({'id': lid, 'notes': note})
            if warnings:
                ambiguous.append({'id': lid, 'reason': warnings, 'ml_extracted': ml})

    with open(output_path, 'w', encoding='utf-8') as out:
        for n in notes:
            out.write(json.dumps(n, ensure_ascii=False) + '\n')
    with open(ambiguous_path, 'w', encoding='utf-8') as aout:
        for a in ambiguous:
            aout.write(json.dumps(a, ensure_ascii=False) + '\n')
    print(f"Wrote {len(notes)} notes to {output_path}, {len(ambiguous)} ambiguous to {ambiguous_path}")


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--in', dest='input', required=True)
    p.add_argument('--out', dest='output', default='notes_to_apply.jsonl')
    p.add_argument('--amb', dest='ambiguous', default='ambiguous_ml.jsonl')
    args = p.parse_args()
    main(args.input, args.output, args.ambiguous)
