#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Apply notes to leads_bruts from a JSONL file with entries: {"id": <int>, "notes": "..."}
Usage:
  python scripts/apply_ml_notes.py --in notes_to_apply.jsonl --dry-run
  python scripts/apply_ml_notes.py --in notes_to_apply.jsonl
"""
import json
import argparse
import sys
import os

# Ensure repo root is in sys.path so imports like `database.connection` work
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from database.connection import get_conn


def apply(input_path, dry_run=True):
    entries = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            entries.append(obj)

    if not entries:
        print("No entries to apply.")
        return

    with get_conn() as conn:
        cur = conn.cursor()
        for e in entries:
            lid = e.get("id")
            notes = e.get("notes")
            if lid is None or notes is None:
                print(f"Skipping invalid entry: {e}")
                continue
            print(f"Apply -> id={lid} notes={notes}")
            if not dry_run:
                cur.execute("UPDATE leads_bruts SET notes=? WHERE id=?", (notes, lid))
        if not dry_run:
            conn.commit()
            print(f"Applied {len(entries)} updates.")
        else:
            print("Dry run only. No DB changes.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="input", required=True, help="JSONL input file")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    apply(args.input, dry_run=args.dry_run)
