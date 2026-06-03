# -*- coding: utf-8 -*-
"""
tools/get_ads_leads_50.py — extrait jusqu'à 50 leads Google Ads en attente
Imprime les lignes et la liste d'IDs en dernière ligne au format `IDS:1,2,3`
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.connection import get_conn

def main(limit=50):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, nom, site_web, source FROM leads_bruts WHERE statut='en_attente' AND (source LIKE '%ads%' OR source LIKE '%google%') ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        if not rows:
            print("NO_LEADS")
            return
        ids = [str(r['id']) for r in rows]
        for r in rows:
            print(f"{r['id']}	{r['nom'] or ''}	{r['site_web'] or ''}	{r['source'] or ''}")
        print("IDS:" + ",".join(ids))

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--limit', type=int, default=50)
    args = p.parse_args()
    main(limit=args.limit)
