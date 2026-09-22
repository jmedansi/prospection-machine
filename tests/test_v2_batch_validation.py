# -*- coding: utf-8 -*-
"""
tests/test_v2_batch_validation.py — validation Telegram PAR LOT des relances v2.

Couvre `core.relance_batch_validator` :
- `ensure_batch_requests` : une seule demande par liste (callback v2_batch_{c}_{l}),
  idempotente (pending → pas de re-demande), absente pour une campagne sans
  `validation_relances`.
- `consume_approvals` : ✅ → run_relances(liste, approval='auto') + statut 'sent' ;
  ❌ → 'refuse', rien n'est envoyé.
Monkeypatch hub Telegram + orchestration (aucun réseau réel).
"""
import pytest

from database import connection as conn_mod


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test_batch.db")
    monkeypatch.setattr(conn_mod, 'DB_PATH', db_path)
    monkeypatch.setattr('database.schema.connection.DB_PATH', db_path)
    from database import schema
    schema.init_db()
    schema.migrate_v2_schema()
    yield db_path


def _campagne(nom='Refonte site web', validation_relances=1):
    from core.objectif_registry import resolve_or_create_campagne
    oid, _ = resolve_or_create_campagne(nom)
    from database.connection import get_conn
    with get_conn() as c:
        c.execute("UPDATE campagnes SET validation_relances=?, envoi_auto=1 WHERE id=?",
                  (validation_relances, oid))
        c.commit()
    return oid


def _prospect(oid, email='contact@dupont.fr'):
    from core.objectif_registry import get_or_create_liste
    from database import prospects_repo
    lid = get_or_create_liste(oid)
    return prospects_repo.insert_prospect(lid, nom='Boulangerie Dupont', email=email,
                                          prenom='M. Dupont', entreprise='Boulangerie Dupont',
                                          secteur='Boulangerie')['prospect_id']


def _seed_template_step(oid, position, delai_jours=0, corps='Corps relance {{prenom}}'):
    from envoi import template_registry
    return template_registry.add_or_update(campagne_id=oid, position=position,
                                           objet=f'Relance pos {position}', corps=corps,
                                           delai_jours=delai_jours)


def _to_en_sequence(pid, oid, days_ago=1):
    from datetime import datetime, timedelta
    from core.state_machine import transition_prospect
    transition_prospect(pid, 'en_sequence', reason='initial (test)')
    from database.connection import get_conn
    ts = (datetime.utcnow() - timedelta(days=days_ago)).strftime('%Y-%m-%d %H:%M:%S')
    with get_conn() as c:
        c.execute("INSERT INTO prospect_events (prospect_id, campagne_id, event_type, payload, created_at) VALUES (?,?,?,?,?)",
                  (pid, oid, 'initial', '{}', ts))
        c.commit()


@pytest.fixture
def fake_hub(monkeypatch):
    """Hub Telegram factice : send_validation_request → 'pending', get_status piloté."""
    store = {'status': {}}
    import core.telegram_adapter as ta

    def _send(outil, preview, callback_id, timeout_minutes=None):
        store['last'] = {'outil': outil, 'preview': preview, 'callback_id': callback_id}
        return 'pending'

    monkeypatch.setattr(ta, 'send_validation_request', _send)
    import envoi.telegram_validation as tv
    monkeypatch.setattr(tv, 'get_status', lambda cb: store['status'].get(cb))
    monkeypatch.setattr(tv, 'mark_completed', lambda cb: True)
    return store


@pytest.fixture
def spy_run_relances(monkeypatch):
    calls = []

    def _run(campagne_id=None, limit_per_campagne=20, manual=False, *, objectif_id=None,
             liste_id=None, approval=None):
        calls.append({'campagne_id': campagne_id, 'liste_id': liste_id, 'approval': approval})
        return {'success': True, 'total': 2, 'runs': []}

    monkeypatch.setattr('core.orchestration.run_relances', _run)
    return calls


def test_aucun_lot_sans_validation_relances(tmp_db, fake_hub):
    oid = _campagne(validation_relances=0)
    _seed_template_step(oid, 1, delai_jours=0)
    pid = _prospect(oid)
    _to_en_sequence(pid, oid)
    from core.relance_batch_validator import ensure_batch_requests
    res = ensure_batch_requests()
    assert res['requests'] == []


def test_un_lot_par_liste_et_idempotence(tmp_db, fake_hub):
    oid = _campagne(validation_relances=1)
    _seed_template_step(oid, 1, delai_jours=0)
    p1 = _prospect(oid, email='a@test.fr')
    p2 = _prospect(oid, email='b@test.fr')
    _to_en_sequence(p1, oid)
    _to_en_sequence(p2, oid)
    from core.relance_batch_validator import ensure_batch_requests, batch_callback
    from database.connection import get_conn
    lid = None
    with get_conn() as c:
        lid = c.execute("SELECT liste_id FROM prospects WHERE id=?", (p1,)).fetchone()[0]
    res = ensure_batch_requests()
    assert len(res['requests']) == 1
    req = res['requests'][0]
    assert req['callback_id'] == batch_callback(oid, lid)
    assert req['campagne_id'] == oid and req['liste_id'] == lid
    assert req['count'] == 2 and req['position'] == 1
    with get_conn() as c:
        row = c.execute("SELECT statut, count FROM relance_batches WHERE callback_id=?",
                        (req['callback_id'],)).fetchone()
        assert row and row[0] == 'pending' and row[1] == 2
    # Idempotence : second passage → aucune nouvelle demande
    store_before = dict(fake_hub.get('last'))
    res2 = ensure_batch_requests()
    assert len(res2['requests']) == 0
    assert fake_hub.get('last') == store_before


def test_consomme_ok_et_envoie_le_lot(tmp_db, fake_hub, spy_run_relances):
    oid = _campagne(validation_relances=1)
    _seed_template_step(oid, 1, delai_jours=0)
    pid = _prospect(oid)
    _to_en_sequence(pid, oid)
    from core.relance_batch_validator import (ensure_batch_requests, consume_approvals,
                                              batch_callback)
    from database.connection import get_conn
    with get_conn() as c:
        lid = c.execute("SELECT liste_id FROM prospects WHERE id=?", (pid,)).fetchone()[0]
    ensure_batch_requests()
    cb = batch_callback(oid, lid)
    fake_hub['status'][cb] = 'ok'
    res = consume_approvals()
    assert len(res['consumed']) == 1 and res['consumed'][0]['statut'] == 'sent'
    assert spy_run_relances == [{'campagne_id': oid, 'liste_id': lid, 'approval': 'auto'}]
    with get_conn() as c:
        assert c.execute("SELECT statut FROM relance_batches WHERE callback_id=?",
                         (cb,)).fetchone()[0] == 'sent'


def test_consomme_no_refuse_sans_envoi(tmp_db, fake_hub, spy_run_relances):
    oid = _campagne(validation_relances=1)
    _seed_template_step(oid, 1, delai_jours=0)
    pid = _prospect(oid)
    _to_en_sequence(pid, oid)
    from core.relance_batch_validator import (ensure_batch_requests, consume_approvals,
                                              batch_callback)
    from database.connection import get_conn
    with get_conn() as c:
        lid = c.execute("SELECT liste_id FROM prospects WHERE id=?", (pid,)).fetchone()[0]
    ensure_batch_requests()
    cb = batch_callback(oid, lid)
    fake_hub['status'][cb] = 'no'
    res = consume_approvals()
    assert len(res['consumed']) == 1 and res['consumed'][0]['statut'] == 'refuse'
    assert spy_run_relances == []
    with get_conn() as c:
        assert c.execute("SELECT statut FROM relance_batches WHERE callback_id=?",
                         (cb,)).fetchone()[0] == 'refuse'
    # Lot refusé à l'identique → ne pas re-demander
    from core.relance_batch_validator import ensure_batch_requests as ensure2
    assert ensure2()['requests'] == []