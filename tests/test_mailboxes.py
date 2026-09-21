# -*- coding: utf-8 -*-
"""
Tests — dashboard/routes/mailboxes.py (listage / quota / actif / reset usage)
et comportement `no_quota` de envoi/gateway.envoyer (email de test → pas de
consommation du quota quotidien de la boîte).

Base SQLite temporaire, aucun envoi réel (dispatch stubé).
"""
import pytest

import database.connection as conn_mod
from database.schema import init_db, migrate_v2_schema


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "prospection_mb_test.db"
    monkeypatch.setattr(conn_mod, 'DB_PATH', db_path)
    monkeypatch.setattr('database.schema.connection.DB_PATH', db_path)
    init_db()
    migrate_v2_schema()
    yield db_path


@pytest.fixture()
def client(tmp_db):
    from dashboard.app import create_app
    app = create_app()
    return app.test_client()


def _add_mailbox(email='mail@zoho.fr', backend='smtp', quota=40, usage=0, actif=1):
    from database.connection import get_conn
    domaine = email.rsplit('@', 1)[-1] if '@' in email else email
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO mailboxes (label, domaine, email, backend, actif, quota_jour, usage_jour)
               VALUES ('Boîte test', ?, ?, ?, ?, ?, ?)""",
            (domaine, email, backend, actif, quota, usage),
        )
        conn.commit()
        return cur.lastrowid


def test_liste_mailboxes_vide(client):
    d = client.get('/api/mailboxes').get_json()
    assert d['success'] is True
    assert d['boites'] == []


def test_liste_affiche_boite_et_champs(client):
    mid = _add_mailbox(quota=60, usage=10)
    d = client.get('/api/mailboxes').get_json()
    assert len(d['boites']) == 1
    b = d['boites'][0]
    assert b['id'] == mid
    assert b['quota_jour'] == 60
    assert b['usage_jour'] == 10
    assert b['actif'] is True
    assert b['email'] == 'mail@zoho.fr'


def test_put_modifie_quota(client):
    mid = _add_mailbox(quota=40, usage=0)
    r = client.put('/api/mailboxes/%s' % mid, json={'quota_jour': 120})
    assert r.get_json()['success'] is True
    b = client.get('/api/mailboxes').get_json()['boites'][0]
    assert b['quota_jour'] == 120


def test_put_quota_invalide(client):
    mid = _add_mailbox(quota=40, usage=0)
    r = client.put('/api/mailboxes/%s' % mid, json={'quota_jour': 'abc'})
    assert r.status_code == 400
    assert 'quota_jour' in r.get_json()['error']


def test_put_boite_inconnue(client):
    r = client.put('/api/mailboxes/987654', json={'quota_jour': 5})
    assert r.status_code == 404


def test_reset_usage(client):
    mid = _add_mailbox(quota=40, usage=40)
    r = client.post('/api/mailboxes/%s/reset' % mid)
    assert r.get_json()['success'] is True
    b = client.get('/api/mailboxes').get_json()['boites'][0]
    assert b['usage_jour'] == 0


def test_desactivation_rend_boite_ineligible(client):
    from envoi.gateway import get_next_mailbox
    mid = _add_mailbox(quota=10, usage=0, actif=0)
    assert get_next_mailbox() is None


def test_ignore_quota_rend_une_boite_pleine_eligible(client):
    from envoi.gateway import get_next_mailbox
    mid = _add_mailbox(quota=40, usage=40)
    assert get_next_mailbox() is None
    m = get_next_mailbox(ignore_quota=True)
    assert m is not None and m['id'] == mid and m['usage_jour'] == 40


def test_envoyer_no_quota_ne_consomme_pas(client, monkeypatch):
    from envoi import gateway
    mid = _add_mailbox(quota=40, usage=7)

    monkeypatch.setattr(gateway, '_dispatch', lambda m, to, msg: {'success': True, 'statut': 'envoye', 'message_id': 'stub'})

    r = gateway.envoyer({'to': 'moi@exemple.fr', 'subject': 'Test', 'corps': 'c', 'dry_run': False, 'no_quota': True})
    assert r['success'] is True
    from database.connection import get_conn
    with get_conn() as conn:
        usage = conn.execute("SELECT usage_jour FROM mailboxes WHERE id = ?", (mid,)).fetchone()[0]
    assert usage == 7

    r2 = gateway.envoyer({'to': 'client@exemple.fr', 'subject': 'S', 'corps': 'c', 'dry_run': False})
    assert r2['success'] is True
    with get_conn() as conn:
        usage = conn.execute("SELECT usage_jour FROM mailboxes WHERE id = ?", (mid,)).fetchone()[0]
    assert usage == 8