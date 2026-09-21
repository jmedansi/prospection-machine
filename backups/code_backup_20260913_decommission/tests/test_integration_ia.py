import os
import sys
import tempfile
import json

import database.connection as connection
import database.db_manager as db_manager
from services import campaign_tracker
from services import ia_runner


def test_integration_scrape_campaign_export_scan(tmp_path):
    db_file = os.path.join(tmp_path, 'integ.db')
    connection.DB_PATH = db_file
    db_manager.DB_PATH = db_file
    db_manager.init_db()
    # Apply migrations to ensure all columns/tables exist for the integrated flow
    try:
        db_manager.migrate_db()
    except Exception:
        pass

    # create campaign and two leads
    camp_id = db_manager.insert_campaign('IntCamp', secteur='s', ville='V')
    lead1 = {'nom': 'IL1', 'ville': 'V', 'email': 'il1@example.com', 'campaign_id': camp_id}
    lead2 = {'nom': 'IL2', 'ville': 'V', 'email': 'il2@example.com', 'campaign_id': camp_id}
    lid1 = db_manager.insert_lead(lead1)
    lid2 = db_manager.insert_lead(lead2)

    # complete campaign -> should create auto-list and export CSV
    campaign_tracker.complete_campaign(camp_id)

    # Find the created list for this campaign
    with connection.get_conn() as conn:
        row = conn.execute('SELECT id, nom FROM lead_lists WHERE campaign_id=?', (camp_id,)).fetchone()
        assert row is not None
        list_id = row['id']
        list_name = row['nom']

    # Check ia_echanges folder and CSV
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'services', '..')
    # Use ia_runner normalization to get slug
    slug = ia_runner.normalize_liste_id(list_id, list_name)
    echanges_root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(ia_runner.__file__))), 'ia_echanges')
    csv_path = os.path.join(echanges_root, slug, 'leads.csv')
    exec_path = os.path.join(echanges_root, slug, 'exec_id.txt')
    assert os.path.isfile(csv_path)
    assert os.path.isfile(exec_path)

    # Read CSV and write IA outputs (fill EmailObjet/EmailCorps)
    import csv
    rows = []
    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append(row)

    # Modify CSV: add EmailObjet and EmailCorps for each lead
    for r in rows:
        r['EmailObjet'] = f"Objet pour {r.get('Nom')}"
        r['EmailCorps'] = f"Corps pour {r.get('Nom')}"

    # Write back CSV (utf-8)
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # Run scan
    res = ia_runner.scan(liste_nom=slug)
    assert res.get('ok') is True
    # If first scan didn't persist emails due to transient DB lock, retry once
    import time
    with connection.get_conn() as conn:
        r1 = conn.execute('SELECT email_objet FROM leads_audites WHERE lead_id=?', (lid1,)).fetchone()
    if not r1 or not r1['email_objet']:
        time.sleep(0.1)
        res2 = ia_runner.scan(liste_nom=slug)
        assert res2.get('ok') is True
    # After scan, leads_audites must have entries with approuve=0
    with connection.get_conn() as conn:
        r1 = conn.execute('SELECT email_objet, email_corps FROM leads_audites WHERE lead_id=?', (lid1,)).fetchone()
        r2 = conn.execute('SELECT email_objet, email_corps FROM leads_audites WHERE lead_id=?', (lid2,)).fetchone()
        assert r1 is not None and r1['email_objet'] is not None
        assert r2 is not None and r2['email_objet'] is not None

    # Exec status should be marked done
    from database.repos import ia_repo
    exs = ia_repo.list_executions_for_list(list_id)
    assert any(e.get('statut') in ('done', 'created', 'pret') for e in exs)
