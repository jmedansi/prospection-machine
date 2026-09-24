# -*- coding: utf-8 -*-
"""
tests/test_v2_validation.py — validation Telegram du pipeline v2.

gating `objectifs.validation_telegram` :
  0 = auto   → envoi direct via gateway
  1 = requis → demande ✅ Telegram → attente → approve_and_send_initial()
On monkeypatche gateway.envoyer (aucun réseau) et telegram_validation (aucun hub réel).
"""
import pytest

from database import connection as conn_mod


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test_prospection.db")
    monkeypatch.setattr(conn_mod, 'DB_PATH', db_path)
    monkeypatch.setattr('database.schema.connection.DB_PATH', db_path)
    from database import schema
    schema.init_db()
    schema.migrate_v2_schema()
    yield db_path


def _objectif(nom='Refonte site web', validation_telegram=0):
    from core.objectif_registry import resolve_or_create_campagne
    oid, nom_r = resolve_or_create_campagne(nom)
    from database.connection import get_conn
    with get_conn() as c:
        c.execute("UPDATE campagnes SET validation_telegram=? WHERE id=?", (validation_telegram, oid))
        c.commit()
    return oid


def _prospect(oid, email='contact@dupont.fr'):
    from core.objectif_registry import get_or_create_liste
    from database import prospects_repo
    lid = get_or_create_liste(oid)
    return prospects_repo.insert_prospect(lid, nom='Boulangerie Dupont', email=email,
                                          prenom='M. Dupont', entreprise='Boulangerie Dupont',
                                          secteur='Boulangerie', site_web='https://dupont.fr')['prospect_id']


@pytest.fixture
def fake_tg(monkeypatch):
    """Un hub Telegram simulé en mémoire, hermétique au pending.db réel."""
    store = {'requested': set(), 'status': {}}
    from envoi import telegram_validation as tv

    def _request(obj, prospect, objet, corps, step_label='Envoi initial'):
        cb = tv.callback_id(prospect['id'])
        store['requested'].add(cb)
        store.setdefault('content', {})[cb] = {'objet': objet, 'corps': corps}
        store['status'][cb] = None
        return {'success': True, 'callback_id': cb}

    def _status(cb):
        return store['status'].get(cb)

    def _requested(cb):
        return cb in store['requested']

    def _complete(cb):
        store['status'][cb] = 'completed'
        return True

    monkeypatch.setattr(tv, 'request', _request)
    monkeypatch.setattr(tv, 'get_status', _status)
    monkeypatch.setattr(tv, 'has_requested', _requested)
    monkeypatch.setattr(tv, 'mark_completed', _complete)
    return store


@pytest.fixture
def fake_gateway(monkeypatch):
    """Envoyo simulé : aucun SMTP/Resend réel, envoi toujours OK."""
    calls = []

    def _envoyer(message, boite=None):
        calls.append(dict(message))
        return {'success': True, 'statut': 'envoye', 'message_id': 'msg-test-123',
                'boite': {'id': 9, 'email': 'boite@test.fr', 'backend': 'resend'}}

    from envoi import gateway as gw
    monkeypatch.setattr(gw, 'envoyer', _envoyer)
    monkeypatch.setattr('envoi.sequence_engine.gateway.envoyer', _envoyer)
    return calls


def test_auto_validation_0_envoi_direct(tmp_db, fake_tg, fake_gateway):
    oid = _objectif(validation_telegram=0)
    pid = _prospect(oid)
    from envoi import sequence_engine as seq
    res = seq.send_initial(oid, pid)
    assert res['success'] and res['statut'] == 'envoye'
    assert len(fake_gateway) == 1
    from database import prospects_repo
    p = prospects_repo.get_prospect(pid)
    assert p['statut'] == 'en_sequence'
    events = [e['event_type'] for e in p['events']]
    assert 'initial' in events
    assert 'validation_requete' not in events


def test_validation_1_demande_puis_attente(tmp_db, fake_tg, fake_gateway):
    oid = _objectif(validation_telegram=1)
    pid = _prospect(oid)
    from envoi import sequence_engine as seq
    res = seq.send_initial(oid, pid)
    assert res['success'] is False and res['statut'] == 'attente_approbation'
    assert res['callback_id'] == f"v2_approve_{pid}"
    assert fake_gateway == []
    from database import prospects_repo
    p = prospects_repo.get_prospect(pid)
    assert p['statut'] == 'qualifie'
    ev = [e for e in p['events'] if e['event_type'] == 'validation_requete']
    assert len(ev) == 1
    payload = ev[0]['payload']
    assert payload['objet'] and payload['corps']
    assert payload['callback_id'] == res['callback_id']


def test_validation_1_demande_non_envoyee_deux_fois(tmp_db, fake_tg, fake_gateway):
    oid = _objectif(validation_telegram=1)
    pid = _prospect(oid)
    from envoi import sequence_engine as seq
    seq.send_initial(oid, pid)
    res2 = seq.send_initial(oid, pid)
    assert res2['statut'] == 'attente_approbation'
    from database import prospects_repo
    p = prospects_repo.get_prospect(pid)
    ev = [e for e in p['events'] if e['event_type'] == 'validation_requete']
    assert len(ev) == 1
    cb = f"v2_approve_{pid}"
    assert cb in fake_tg['requested']


def test_approbation_ok_declenche_envoi(tmp_db, fake_tg, fake_gateway):
    oid = _objectif(validation_telegram=1)
    pid = _prospect(oid)
    from envoi import sequence_engine as seq
    first = seq.send_initial(oid, pid)
    assert first['statut'] == 'attente_approbation'

    fake_tg['status'][first['callback_id']] = 'ok'
    res = seq.approve_and_send_initial(pid)
    assert res['success'] and res['statut'] == 'envoye'
    assert len(fake_gateway) == 1
    assert fake_tg['status'][first['callback_id']] == 'completed'

    from database import prospects_repo
    p = prospects_repo.get_prospect(pid)
    assert p['statut'] == 'en_sequence'
    types = [e['event_type'] for e in p['events']]
    assert 'initial' in types
    initial = [e for e in p['events'] if e['event_type'] == 'initial'][-1]
    payload = initial['payload']
    assert payload['mailbox_email'] == 'boite@test.fr'
    assert payload['backend'] == 'resend'


def test_send_initial_passe_sur_validation_preciseement_approuvee(tmp_db, fake_tg, fake_gateway):
    """Si la validation est déjà approuvée au moment de send_initial, envoi direct."""
    oid = _objectif(validation_telegram=1)
    pid = _prospect(oid)
    from envoi import sequence_engine as seq
    first = seq.send_initial(oid, pid)
    assert first['statut'] == 'attente_approbation'

    fake_tg['status'][first['callback_id']] = 'ok'
    res = seq.send_initial(oid, pid)  # ré-élection du scheduler → OK consommé
    assert res['success'] and res['statut'] == 'envoye'
    assert len(fake_gateway) == 1
    assert fake_tg['status'][first['callback_id']] == 'completed'


def test_refus_telegram_bloque(tmp_db, fake_tg, fake_gateway):
    oid = _objectif(validation_telegram=1)
    pid = _prospect(oid)
    from envoi import sequence_engine as seq
    first = seq.send_initial(oid, pid)
    fake_tg['status'][first['callback_id']] = 'ko'
    res = seq.send_initial(oid, pid)
    assert res['success'] is False and res['statut'] == 'validation_refusee'
    assert fake_gateway == []
    from database import prospects_repo
    assert prospects_repo.get_prospect(pid)['statut'] == 'qualifie'


def test_approbation_sans_demande_prealable(tmp_db, fake_tg, fake_gateway):
    oid = _objectif(validation_telegram=1)
    pid = _prospect(oid)
    from envoi import sequence_engine as seq
    res = seq.approve_and_send_initial(pid)
    assert res['success'] is False and res['status'] == 'sans_demande'
    assert fake_gateway == []