# -*- coding: utf-8 -*-
"""
tests/test_v2_orchestration.py — orchestration des envois initiaux v2.

- kill-switch global (`planning_settings.v2_auto_send`) : coupé → rien ne tourne.
- `objectifs.envoi_auto` : 0 = l'objectif ne participe pas à l'auto-send,
  1 = il est dans le lot.
- `manual=True` (POST /api/v2/objectifs/<id>/send) : bypass global + envoi_auto.
Monkeypatch gateway (aucun réseau), humanisation court-circuitée par dry physics.
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


def _objectif(nom='Refonte site web', envoi_auto=1, validation_telegram=0):
    from core.objectif_registry import resolve_or_create_campagne
    cid, _nom = resolve_or_create_campagne(nom)
    from database.connection import get_conn
    with get_conn() as c:
        c.execute("UPDATE campagnes SET envoi_auto=?, validation_telegram=? WHERE id=?", (envoi_auto, validation_telegram, cid))
        c.commit()
    return cid


def _prospect(cid, email='contact@dupont.fr', oppose=False, ecarte=False):
    from core.objectif_registry import get_or_create_liste
    from database import prospects_repo
    lid = get_or_create_liste(cid)
    pid = prospects_repo.insert_prospect(lid, nom='Boulangerie Dupont', email=email,
                                         entreprise='Boulangerie Dupont', secteur='Boulangerie',
                                         data_extra={
                                             # Source de vérité du tunnel v2 : l'email RÉDIGÉ.
                                             'email_objet': 'Une proposition pour {{entreprise}}',
                                             'email_corps': 'Bonjour,\n\nVoici ma proposition.',
                                         })['prospect_id']
    from database.connection import get_conn
    with get_conn() as c:
        if oppose:
            c.execute("UPDATE prospects SET ne_plus_contacter=1, statut='ne_plus_contacter' WHERE id=?", (pid,))
        if ecarte:
            c.execute("UPDATE prospects SET ecarte=1 WHERE id=?", (pid,))
        c.commit()
    return pid


@pytest.fixture
def fake_gateway(monkeypatch):
    calls = []

    def _envoyer(message, boite=None):
        calls.append(dict(message))
        return {'success': True, 'statut': 'envoye', 'message_id': 'msg-orto',
                'boite': {'id': 9, 'email': 'boite@test.fr', 'backend': 'smtp'}}

    from envoi import gateway as gw
    monkeypatch.setattr(gw, 'envoyer', _envoyer)
    monkeypatch.setattr('envoi.sequence_engine.gateway.envoyer', _envoyer)
    return calls


def test_candidates_fifo_exclusions_et_limit(tmp_db):
    oid = _objectif()
    p1 = _prospect(oid, email='a@test.fr')
    _prospect(oid, email='b@test.fr', oppose=True)
    _prospect(oid, email='c@test.fr', ecarte=True)
    _prospect(oid, email='')   # pas d'email → exclu
    p4 = _prospect(oid, email='d@test.fr')
    from database.connection import get_conn
    with get_conn() as c:
        c.execute("INSERT INTO suppression_list (email, raison) VALUES ('d@test.fr', 'desinscription')")
        c.commit()
    from core.orchestration import candidates_for
    ids = [r['id'] for r in candidates_for(oid, limit=10)]
    assert ids == [p1], f"a={p1}, d={p4}: {ids}"
    assert candidates_for(oid, limit=1)[0]['id'] == p1


def test_enabled_objectifs_ignore_envoi_auto_0(tmp_db):
    oid_on = _objectif('Auto ON', envoi_auto=1)
    oid_off = _objectif('Auto OFF', envoi_auto=0)
    from core.orchestration import enabled_objectifs
    seule = [o['id'] for o in enabled_objectifs()]
    assert oid_on in seule and oid_off not in seule


def test_kill_switch_global_arrete_tout(tmp_db, fake_gateway):
    oid = _objectif()
    _prospect(oid)
    from database import campagnes as campagnes_repo
    campagnes_repo.set_auto_send_enabled(False)
    from core.orchestration import run_auto_send
    # Règle 2026-09 : run_auto_send SANS manual=True est TOUJOURS refusé
    res = run_auto_send()
    assert res['quoted'] == 'initial_manuel_obligatoire'
    assert res['runs'] == []
    assert fake_gateway == []


def test_scheduler_ignore_objectif_envoi_auto_0(tmp_db, fake_gateway, monkeypatch):
    oid_off = _objectif('Manuel', envoi_auto=0)
    _prospect(oid_off)
    from database import campagnes as campagnes_repo
    campagnes_repo.set_auto_send_enabled(True)
    from core.orchestration import run_auto_send
    # auto-send d'initial supprimé : rien ne part sans manual=True
    res = run_auto_send()
    assert res['quoted'] == 'initial_manuel_obligatoire'
    assert fake_gateway == []


def test_auto_send_envoie_et_respecte_validation(tmp_db, monkeypatch, fake_gateway):
    oid = _objectif(validation_telegram=0)
    pid = _prospect(oid)
    from database import campagnes as campagnes_repo
    campagnes_repo.set_auto_send_enabled(True)
    from core.orchestration import run_auto_send
    # pas de manual=True → refus, rien envoyé
    res = run_auto_send()
    assert res['success'] and res['quoted'] == 'initial_manuel_obligatoire'
    assert res['runs'] == []
    assert fake_gateway == []


def test_manual_bypass_global_et_envoi_auto(tmp_db, fake_gateway):
    oid = _objectif('Manuel', envoi_auto=0)
    pid = _prospect(oid)
    from database import campagnes as campagnes_repo
    campagnes_repo.set_auto_send_enabled(False)
    from core.orchestration import run_auto_send
    res = run_auto_send(objectif_id=oid, manual=True)
    assert res['total'] == 1
    assert res['runs'][0]['details'][0]['statut'] == 'envoye'
    assert len(fake_gateway) == 1
    from database import prospects_repo
    assert prospects_repo.get_prospect(pid)['statut'] == 'en_sequence'


def test_manual_sans_force_ignore_lobjectif(tmp_db, fake_gateway):
    oid = _objectif('Manuel', envoi_auto=0)
    _prospect(oid)
    from database import campagnes as campagnes_repo
    campagnes_repo.set_auto_send_enabled(True)
    from core.orchestration import run_auto_send
    res = run_auto_send(objectif_id=oid)   # pas de manual= True
    assert res.get('quoted') == 'initial_manuel_obligatoire'
    assert fake_gateway == []


def test_auto_send_avec_validation_demande_sans_envoi(tmp_db, monkeypatch, fake_gateway):
    oid = _objectif(validation_telegram=1)
    pid = _prospect(oid)
    # hub Telegram simulé : demande acceptée, jamais approuvée
    store = {'requested': set(), 'status': {}}
    from envoi import telegram_validation as tv

    def _request(obj, prospect, objet, corps, step_label='Envoi initial'):
        cb = f"v2_approve_{prospect['id']}"
        store['requested'].add(cb)
        store['status'][cb] = None
        return {'success': True, 'callback_id': cb}

    monkeypatch.setattr(tv, 'request', _request)
    monkeypatch.setattr(tv, 'get_status', lambda cb: store['status'].get(cb))
    monkeypatch.setattr(tv, 'has_requested', lambda cb: cb in store['requested'])
    monkeypatch.setattr(tv, 'mark_completed', lambda cb: True)

    from database import campagnes as campagnes_repo
    campagnes_repo.set_auto_send_enabled(True)
    from core.orchestration import run_auto_send
    # sans manual=True → refus structurel, aucun envoi
    res = run_auto_send()
    assert res['quoted'] == 'initial_manuel_obligatoire'
    assert res['runs'] == []
    assert fake_gateway == []  # rien envoyé


def test_kill_switch_se_relit_depuis_la_base(tmp_db):
    from database import campagnes as campagnes_repo
    assert campagnes_repo.get_auto_send_enabled() is True
    campagnes_repo.set_auto_send_enabled(False)
    assert campagnes_repo.get_auto_send_enabled() is False
    campagnes_repo.set_auto_send_enabled(True)
    assert campagnes_repo.get_auto_send_enabled() is True