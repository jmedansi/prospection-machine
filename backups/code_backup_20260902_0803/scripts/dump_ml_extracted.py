#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Export ml_extracted from leads_bruts as JSONL.
Usage:
  python scripts/dump_ml_extracted.py --out ml_extracted_dump.jsonl --limit 200
  python scripts/dump_ml_extracted.py --ids 123,456
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


def dump(output_path=None, ids=None, limit=None):
    q = "SELECT id, nom, site_web, ml_extracted FROM leads_bruts WHERE ml_extracted IS NOT NULL AND ml_extracted != ''"
    params = []
    if ids:
        placeholders = ",".join("?" for _ in ids)
        q = f"SELECT id, nom, site_web, ml_extracted FROM leads_bruts WHERE id IN ({placeholders})"
        params = ids
    elif limit:
        q += " LIMIT ?"
        params = [limit]

    with get_conn() as conn:
        rows = conn.execute(q, params).fetchall()

    lines = []
    for r in rows:
        lid = r["id"]
        try:
            ml = json.loads(r["ml_extracted"]) if r["ml_extracted"] else {"raw_text": None}
        except Exception:
            ml = {"raw_text": None}
        obj = {"id": lid, "nom": r["nom"], "site_web": r["site_web"], "ml_extracted": ml}
        lines.append(json.dumps(obj, ensure_ascii=False))
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"Wrote {len(lines)} lines to {output_path}")
    else:
        print("\n".join(lines))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", help="Fichier de sortie (jsonl)")
    p.add_argument("--limit", type=int, help="Limiter le nombre de leads")
    p.add_argument("--ids", help="Liste d'ids séparés par des virgules (ex: 12,34,56)")
    args = p.parse_args()
    ids = [int(x.strip()) for x in args.ids.split(",")] if args.ids else None
    dump(args.out, ids=ids, limit=args.limit)
