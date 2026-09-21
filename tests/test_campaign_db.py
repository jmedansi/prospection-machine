import os
import sys
import tempfile
import types
import sqlite3
import pytest

# Ensure project root in path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import database.connection as connection
import database.db_manager as db_manager
import services.campaign_tracker as campaign_tracker


def setup_temp_db():
    tmpf = tempfile.NamedTemporaryFile(delete=False)
    tmpf.close()
    db_path = tmpf.name
    # point DB_PATH in both modules
    connection.DB_PATH = sqlite3.Path(db_path) if hasattr(sqlite3, 'Path') else db_path
    db_manager.DB_PATH = db_path
    # Initialize DB
    db_manager.init_db()
    return db_path


class DummyIARunner:
    def __init__(self):
        self.calls = []
    def export(self, liste_id=None, liste_nom=None, lead_ids=None, objectif="tous", moteur="file"):
        self.calls.append({'liste_id': liste_id, 'liste_nom': liste_nom, 'lead_ids': lead_ids, 'objectif': objectif})
        return {'ok': True}


def test_insert_lead_updates_duplicate_and_creates_list(tmp_path):
    db_file = os.path.join(tmp_path, 'test.db')
    connection.DB_PATH = db_file
    db_manager.DB_PATH = db_file
    db_manager.init_db()

    # create a campaign
    camp_id = db_manager.insert_campaign('TestCamp', secteur='test', ville='X', nb_demande=1)
    assert isinstance(camp_id, int)

    lead = {
        'nom': 'Chez Toto',
        'ville': 'X',
        'email': 'toto@example.com',
    }
    # first insert
    lid = db_manager.insert_lead(lead)
    assert isinstance(lid, int)

    # insert duplicate with campaign_id; should return same id and associate with lead_list
    lead2 = lead.copy()
    lead2['campaign_id'] = camp_id
    lid2 = db_manager.insert_lead(lead2)
    assert lid2 == lid

    # check lead_lists association
    with connection.get_conn() as conn:
        rl = conn.execute('SELECT id FROM lead_lists WHERE campaign_id=?', (camp_id,)).fetchone()
        assert rl is not None
        list_id = rl['id']
        rr = conn.execute('SELECT lead_id FROM lead_list_items WHERE list_id=? AND lead_id=?', (list_id, lid)).fetchone()
        assert rr is not None


def test_complete_campaign_triggers_export(tmp_path, monkeypatch):
    db_file = os.path.join(tmp_path, 'test2.db')
    connection.DB_PATH = db_file
    db_manager.DB_PATH = db_file
    db_manager.init_db()

    # create campaign and two leads
    camp_id = db_manager.insert_campaign('Camp2', secteur='s', ville='V')
    lead1 = {'nom': 'L1', 'ville': 'V', 'email': 'l1@example.com', 'campaign_id': camp_id}
    lead2 = {'nom': 'L2', 'ville': 'V', 'email': 'l2@example.com', 'campaign_id': camp_id}
    lid1 = db_manager.insert_lead(lead1)
    lid2 = db_manager.insert_lead(lead2)

    # inject dummy ia_runner into services package
    dummy = DummyIARunner()
    import services
    sys.modules['services.ia_runner'] = dummy
    setattr(services, 'ia_runner', dummy)

    # call complete_campaign
    campaign_tracker.complete_campaign(camp_id)

    # ensure a lead_list was created and dummy.export was called
    assert len(dummy.calls) >= 1
    call = dummy.calls[-1]
    assert call['lead_ids'] is None or isinstance(call['lead_ids'], list) or call['liste_id'] is not None
