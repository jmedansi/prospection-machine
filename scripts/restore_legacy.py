# -*- coding: utf-8 -*-
"""
scripts/restore_legacy.py — Restaure les données legacy (backup 2026-09-12) dans le v2.

Source    : data/backup/prospection_20260912_235735.db (lecture seule)
  - lead_lists   → listes v2 (nom, description, note, icone, couleur, objectif)
  - leads_bruts  → prospects v2 (champs métier + notes → prospects.note)
  - leads_audites→ enrichissement data_extra (scores, rapport, template…)
  - provenance   → prospect_events (event_type='import', payload legacy_id…)

3 campagnes cibles (créées si absentes, envoi_auto=0) :
  - 🗺️ Restauration — Maps   (source lead : maps / maps,ads)
  - 🔫 Restauration — Sniper (source lead : ads / jobs)
  - 🎓 Restauration — Écoles (source lead : edutrack_manual)

La campagne est déterminée par la source MAJORITAIRE des leads de chaque liste legacy.
Les leads sans liste (orphelins) → liste « 📥 Leads orphelins (sans liste) » (Maps).

SÉCURITÉ :
  - Tous les prospects restaurés sont posés en ecarte=1 (archivés, exclus des envois).
  - Les 3 campagnes cibles sont en envoi_auto=0 (jamais de send automatique).
  - Idempotent : marqueur planning_settings.legacy_restore_20260912 → re-run = skip.
  - suppression_list (globale) respectée : les emails opt-out ne sont pas restaurés.

Usage : python scripts/restore_legacy.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

from database.connection import get_conn
from database import campagnes as campagnes_repo
from database import listes as listes_repo
from database import prospects as prospects_repo
from core import objectif_registry

BACKUP_PATH = Path(__file__).resolve().parent.parent / "data" / "backup" / "prospection_20260912_235735.db"
MARKER_KEY = "legacy_restore_20260912"

CAMPAGNES = {
    'maps':   '🗺️ Restauration — Maps',
    'sniper': '🔫 Restauration — Sniper',
    'ecoles': '🎓 Restauration — Écoles',
}
SOURCE_TO_CAMPAGNE = {
    'maps':          'maps',
    'maps,ads':      'maps',
    'ads':           'sniper',
    'jobs':          'sniper',
    'edutrack_manual': 'ecoles',
}
SOURCE_LABEL = {'maps': 'legacy_maps', 'sniper': 'legacy_sniper', 'ecoles': 'legacy_ecoles'}

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
MAX_EXTRA = 1500


def _truncate(s, n=MAX_EXTRA):
    if s is None or s == '':
        return None
    s = str(s)
    return s if len(s) <= n else s[:n]


def _empty(val):
    return val is None or val == ''


def _pick_email(lb):
    for c in (lb['email_valide'], lb['email']):
        if c and EMAIL_RE.match(c.strip()):
            return c.strip()
    return (lb['email'] or '').strip()


def adapt_lead(lb, audit):
    """Adapte un lead legacy (leads_bruts + leads_audites) au format rows de bulk_import."""
    business = (lb['nom'] or '').strip()
    nom_gerant = (lb['nom_gerant'] or '').strip()
    prenom_gerant = (lb['prenom_gerant'] or '').strip()
    if nom_gerant:
        nom = nom_gerant
        entreprise = business
    else:
        nom = business
        entreprise = business or None

    secteurs = [lb['categorie'], lb['category'], lb['secteur']]
    secteur = next((s for s in secteurs if not _empty(s)), None)

    score = None
    if audit and audit['mobile_score'] is not None:
        score = audit['mobile_score']
    elif lb['ia_score'] is not None:
        score = lb['ia_score']

    extra = {
        'legacy_id': lb['id'],
        'legacy_table': 'leads_bruts',
        'campaign_legacy_id': lb['campaign_id'],
        'source_legacy': lb['source'],
        'statut_legacy': lb['statut'],
        'categorie': secteur,
        'mot_cle': _truncate(lb['mot_cle'], 200),
        'lien_maps': _truncate(lb['lien_maps'], 500),
        'logo_url': _truncate(lb['logo_url'], 500),
        'pays': lb['pays'],
        'email_2': lb['email_2'],
        'telephone_2': lb['telephone_2'],
        'linkedin_url': _truncate(lb['linkedin_url'], 500),
        'ml_extracted': _truncate(lb['ml_extracted'], 500),
        'date_scraping': lb['date_scraping'],
        'ia_score': lb['ia_score'],
        'ia_opportunite': _truncate(lb['ia_opportunite'], 500),
        'tag_urgence': lb['tag_urgence'],
        'niveau_urgence': lb['niveau_urgence'],
        'ecarte_legacy': lb['ecarte'],
    }
    if audit:
        extra.update({
            'mobile_score': audit['mobile_score'],
            'desktop_score': audit['desktop_score'],
            'score_performance': audit['score_performance'],
            'score_seo': audit['score_seo'],
            'score_gmb': audit['score_gmb'],
            'score_urgence': audit['score_urgence'],
            'probleme_principal': _truncate(audit['probleme_principal'], 400),
            'service_suggere': _truncate(audit['service_suggere'], 400),
            'top3_problems': _truncate(audit['top3_problems'], 600),
            'rapport_resume': _truncate(audit['rapport_resume']),
            'approuve': audit['approuve'],
            'template_used': audit['template_used'],
            'template_variant': audit['template_variant'],
            'profile': audit['profile'],
            'email_source': audit['email_source'],
            'statut_prospection': audit['statut_prospection'],
            'ceo_prenom': audit['ceo_prenom'],
            'ceo_nom': audit['ceo_nom'],
            'date_audit': audit['date_audit'],
            'lien_rapport': _truncate(audit['lien_rapport'], 500),
        })
    extra = {k: v for k, v in extra.items() if not _empty(v)}

    return {
        'nom': nom,
        'prenom': prenom_gerant or None,
        'email': _pick_email(lb),
        'telephone': lb['telephone'],
        'entreprise': entreprise,
        'site_web': lb['site_web'],
        'adresse': lb['adresse'],
        'ville': lb['ville'],
        'secteur': secteur,
        'rating': lb['rating'],
        'nb_avis': lb['nb_avis'],
        'score': score,
        'data_extra': extra,
        '_legacy_id': lb['id'],
        '_note': (lb['notes'] or '').strip(),
        '_statut_legacy': lb['statut'],
    }


def classer_liste(conn, liste_id):
    """Retourne la clé campagne d'une liste legacy (source majoritaire de ses leads)."""
    rows = conn.execute(
        """SELECT lb.source, COUNT(*) AS n FROM lead_list_items lli
           JOIN leads_bruts lb ON lb.id = lli.lead_id
           WHERE lli.list_id = ? GROUP BY lb.source ORDER BY n DESC""",
        (liste_id,),
    ).fetchall()
    if not rows:
        return 'maps'
    dominant = rows[0]['source'] or ''
    return SOURCE_TO_CAMPAGNE.get(dominant, 'maps')


def marker_done(conn):
    row = conn.execute("SELECT value FROM planning_settings WHERE key = ?", (MARKER_KEY,)).fetchone()
    return row['value'] if row else None


def main():
    ap = argparse.ArgumentParser(description="Restaure les données legacy (backup 2026-09-12) dans le v2.")
    ap.add_argument('--dry-run', action='store_true', help="Affiche le plan sans écrire dans la base v2")
    args = ap.parse_args()
    dry = args.dry_run

    if not BACKUP_PATH.exists():
        print(f"[ERREUR] Backup introuvable : {BACKUP_PATH}")
        return 1

    with get_conn() as conn:
        already = marker_done(conn)
    if already and not dry:
        print(f"[SKIP] Restauration déjà effectuée ({already})."
              f" Pour relancer, supprime planning_settings.{MARKER_KEY}.")
        return 0

    src = sqlite3.connect(f"file:{BACKUP_PATH.as_posix()}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    print(f"[BACKUP] {BACKUP_PATH.name}")

    audits = {}
    for a in src.execute("SELECT * FROM leads_audites ORDER BY lead_id, id").fetchall():
        audits.setdefault(a['lead_id'], a)

    listes_legacy = src.execute("SELECT * FROM lead_lists ORDER BY id").fetchall()

    plan = Counter()
    for ll in listes_legacy:
        key = classer_liste(src, ll['id'])
        n = src.execute("SELECT COUNT(*) AS n FROM lead_list_items WHERE list_id = ?", (ll['id'],)).fetchone()['n']
        plan[key] += 1
        print(f"  [PLAN] {key:<6} liste #{ll['id']:<3} n={n:<4} « {ll['nom'][:60]} »")

    orphelins = src.execute(
        "SELECT COUNT(*) AS n FROM leads_bruts WHERE id NOT IN (SELECT DISTINCT lead_id FROM lead_list_items)"
    ).fetchone()['n']
    print(f"  [PLAN] orphelins (sans liste) n={orphelins}")
    print(f"==> {dict(plan)} listes legacy à restaurer ({sum(plan.values())} total)")

    if dry:
        print("\n[dry-run] Aucune écriture.")
        src.close()
        return 0

    campagnes_ids = {}
    for key, nom_campagne in CAMPAGNES.items():
        res = objectif_registry.resolve_or_create_campagne(nom_campagne)
        if not res:
            print(f"[ERREUR] Impossible de créer la campagne « {nom_campagne} »")
            return 1
        camp_id, _ = res
        if campagnes_repo.get_campagne(camp_id).get('envoi_auto', 1):
            campagnes_repo.update_campagne(camp_id, envoi_auto=0)
        with get_conn() as conn:
            default_rows = conn.execute(
                "SELECT id FROM listes WHERE campagne_id = ? AND nom = ?", (camp_id, nom_campagne)
            ).fetchall()
        for drow in default_rows:
            listes_repo.delete_liste(drow['id'])
        print(f"[CAMPAGNE] « {nom_campagne} » → id #{camp_id}")
        campagnes_ids[key] = camp_id

    totals = {'importes': 0, 'doublons': 0, 'supprimes': 0, 'errors': 0, 'listes': 0}
    notes_count = 0

    for ll in listes_legacy:
        key = classer_liste(src, ll['id'])
        camp_id = campagnes_ids[key]
        res = listes_repo.create_liste(
            camp_id,
            ll['nom'],
            description=(ll['description'] or '') or None,
            note=(ll['note'] or ''),
            icone=(ll['icone'] or '📋'),
            couleur=(ll['couleur'] or '#6366f1'),
            objectif=(ll['objectif'] or 'general'),
            source='legacy',
            statut='actif',
        )
        if not res.get('success'):
            print(f"  [ERREUR] liste #{ll['id']} « {ll['nom']} » : {res.get('error')}")
            totals['errors'] += 1
            continue
        liste_id = res['liste']['id']

        lead_ids = [r['lead_id'] for r in src.execute(
            "SELECT lead_id FROM lead_list_items WHERE list_id = ? ORDER BY id", (ll['id'],)
        )]
        leads = {}
        rows = []
        for lid in lead_ids:
            lb = src.execute("SELECT * FROM leads_bruts WHERE id = ?", (lid,)).fetchone()
            if not lb:
                continue
            leads[lid] = lb
            rows.append(adapt_lead(lb, audits.get(lid)))

        stats = prospects_repo.bulk_import(liste_id, rows, source=SOURCE_LABEL[key])
        totals['importes'] += stats['importes']
        totals['doublons'] += stats['doublons']
        totals['supprimes'] += stats['supprimes']
        totals['errors'] += stats['errors']
        totals['listes'] += 1

        imported = [(row, ent) for row, ent in zip(rows, stats['liste']) if ent.get('prospect_id')]
        _patch_prospects(imported, camp_id, ll['nom'])
        n_notes = sum(1 for row, ent in imported if row.get('_note'))
        notes_count += n_notes
        print(f"  [LISTE] #{ll['id']} « {ll['nom'][:55]} » → v2#{liste_id} "
              f"(+{stats['importes']}/doublon {stats['doublons']}/suppr {stats['supprimes']}/err {stats['errors']}, notes {n_notes})")

    if orphelins:
        camp_id = campagnes_ids['maps']
        res = listes_repo.create_liste(
            camp_id, '📥 Leads orphelins (sans liste)',
            description='Leads legacy présents dans leads_bruts sans liste (backup 2026-09-12)',
            note='', icone='📥', couleur='#64748b', objectif='general', source='legacy', statut='actif',
        )
        if res.get('success'):
            liste_id = res['liste']['id']
            rows = [adapt_lead(lb, audits.get(lb['id']))
                    for lb in src.execute(
                        "SELECT * FROM leads_bruts WHERE id NOT IN (SELECT DISTINCT lead_id FROM lead_list_items)"
                    ).fetchall()]
            stats = prospects_repo.bulk_import(liste_id, rows, source='legacy_maps')
            totals['importes'] += stats['importes']
            totals['doublons'] += stats['doublons']
            totals['supprimes'] += stats['supprimes']
            totals['errors'] += stats['errors']
            totals['listes'] += 1
            imported = [(row, ent) for row, ent in zip(rows, stats['liste']) if ent.get('prospect_id')]
            _patch_prospects(imported, camp_id, '📥 Leads orphelins (sans liste)')
            notes_count += sum(1 for row, ent in imported if row.get('_note'))
            print(f"  [ORPHELINS] v2#{liste_id} (+{stats['importes']}/doublon {stats['doublons']}/suppr {stats['supprimes']}/err {stats['errors']})")

    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO planning_settings (key, value) VALUES (?, ?)",
                     (MARKER_KEY, now))
        conn.commit()

    print("\n[RÉSUMÉ]")
    print(f"  campagnes : {len(campagnes_ids)} (Maps / Sniper / Écoles, envoi_auto=0)")
    print(f"  listes v2 créées : {totals['listes']}")
    print(f"  prospects importés : {totals['importes']} (ecarte=1)")
    print(f"  doublons ignorés : {totals['doublons']} | suppression_list : {totals['supprimes']} | erreurs : {totals['errors']}")
    print(f"  prospects avec note restaurée : {notes_count}")
    src.close()
    return 0


def _patch_prospects(imported, campagne_id, nom_liste):
    """Pose note + ecarte=1 et journalise la provenance legacy (prospect_events)."""
    if not imported:
        return
    now = datetime.now().isoformat(timespec='seconds')
    note_rows = []
    events = []
    for row, ent in imported:
        pid = ent['prospect_id']
        note_rows.append((row.get('_note') or '', 1, pid))
        events.append((
            pid, campagne_id, 'import',
            json.dumps({
                'legacy_id': row.get('_legacy_id'),
                'legacy_table': 'leads_bruts',
                'nom_liste_legacy': nom_liste,
                'statut_legacy': row.get('_statut_legacy'),
                'note': (row.get('_note') or '')[:500],
                'restaure_le': now.split('T')[0],
            }, ensure_ascii=False),
        ))
    with get_conn() as conn:
        conn.executemany("UPDATE prospects SET note = ?, ecarte = ? WHERE id = ?", note_rows)
        conn.executemany(
            "INSERT INTO prospect_events (prospect_id, campagne_id, event_type, payload) VALUES (?, ?, ?, ?)",
            events)
        conn.commit()


if __name__ == '__main__':
    sys.exit(main())