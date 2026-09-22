# -*- coding: utf-8 -*-
"""
tests/test_v2_relances.py — relances v2 (positions > 0 du registre de templates).

- `relances_due` : statut en_sequence/relance_1/relance_2 + dernière touche +
  delai_jours du template suivant ≤ maintenant.
- `send_relance` : même tunnel que l'initial (template position N, humanisation,
  validation Telegram, max_touches) + transition machine à états.
Monkeypatch gateway + hub Telegram (aucun réseau réel).
"""
from datetime import datetime, timedelta

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


def _objectif(nom='Refonte site web', validation_telegram=0, max_touches=3):
    from core.objectif_registry import resolve_or_create_campagne
    oid, _ = resolve_or_create_campagne(nom)
    from database.connection import get_conn
    with get_conn() as c:
        c.execute("UPDATE campagnes SET validation_telegram=?, max_touches=? WHERE id=?", (validation_telegram, max_touches, oid))
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


def _to_en_sequence(pid, oid, days_ago=0):
    """Simule un initial déjà envoyé : transition + event 'initial' daté."""
    from core.state_machine import transition_prospect
    transition_prospect(pid, 'en_sequence', reason='initial (test)')
    from database.connection import get_conn
    ts = (datetime.utcnow() - timedelta(days=days_ago)).strftime('%Y-%m-%d %H:%M:%S')
    with get_conn() as c:
        c.execute("UPDATE prospects SET updated_at=? WHERE id=?", (ts, pid))
        c.execute("INSERT INTO prospect_events (prospect_id, campagne_id, event_type, payload, created_at) VALUES (?,?,?,?,?)",
                  (pid, oid, 'initial', '{}', ts))
        c.commit()


def _to_en_sequence_at(pid, oid, ts):
    """Idem avec un horodatage explicite (tests jours ouvrés)."""
    from core.state_machine import transition_prospect
    transition_prospect(pid, 'en_sequence', reason='initial (test)')
    from database.connection import get_conn
    with get_conn() as c:
        c.execute("UPDATE prospects SET updated_at=? WHERE id=?", (ts, pid))
        c.execute("INSERT INTO prospect_events (prospect_id, campagne_id, event_type, payload, created_at) VALUES (?,?,?,?,?)",
                  (pid, oid, 'initial', '{}', ts))
        c.commit()


@pytest.fixture
def fake_gateway(monkeypatch):
    calls = []

    def _envoyer(message, boite=None):
        calls.append(dict(message))
        return {'success': True, 'statut': 'envoye', 'message_id': 'msg-rel',
                'boite': {'id': 9, 'email': 'boite@test.fr', 'backend': 'smtp'}}

    from envoi import gateway as gw
    monkeypatch.setattr(gw, 'envoyer', _envoyer)
    monkeypatch.setattr('envoi.sequence_engine.gateway.envoyer', _envoyer)
    return calls


@pytest.fixture
def fake_tg(monkeypatch):
    store = {'requested': set(), 'status': {}}
    from envoi import telegram_validation as tv

    def _request(obj, prospect, objet, corps, step_label='Envoi initial'):
        cb = tv.callback_id(prospect['id'])
        store['requested'].add(cb)
        store.setdefault('content', {})[cb] = {'objet': objet, 'corps': corps}
        store['status'][cb] = None
        return {'success': True, 'callback_id': cb}

    monkeypatch.setattr(tv, 'request', _request)
    monkeypatch.setattr(tv, 'get_status', lambda cb: store['status'].get(cb))
    monkeypatch.setattr(tv, 'has_requested', lambda cb: cb in store['requested'])
    monkeypatch.setattr(tv, 'mark_completed', lambda cb: True)
    monkeypatch.setattr(tv, 'reset_for_prospect', lambda pid: store['status'].pop(
        tv.callback_id(pid), None))
    return store


def test_relances_due_respecte_delai(tmp_db, fake_gateway):
    oid = _objectif()
    _seed_template_step(oid, 1, delai_jours=0)
    p_bientot = _prospect(oid, email='a@test.fr')
    p_tard = _prospect(oid, email='b@test.fr')
    _to_en_sequence(p_bientot, oid, days_ago=0)   # relance 1 due immédiatement
    _to_en_sequence(p_tard, oid, days_ago=0)      # idem (delai 0)
    from core.orchestration import relances_due
    due = {d['id'] for d in relances_due(oid)}
    assert p_bientot in due and p_tard in due
    # délai long : rien de dû (J-2 < 10 jours)
    from envoi import template_registry
    pos1 = template_registry.get_step(oid, position=1)
    if pos1:
        template_registry.delete(pos1['id'])
    _seed_template_step(oid, 1, delai_jours=10)
    p3 = _prospect(oid, email='c@test.fr')
    _to_en_sequence(p3, oid, days_ago=2)
    due2 = {d['id'] for d in relances_due(oid)}
    assert p3 not in due2


def test_send_relance_auto_transitionne(tmp_db, fake_gateway):
    oid = _objectif(validation_telegram=0)
    _seed_template_step(oid, 1, delai_jours=0)
    pid = _prospect(oid)
    _to_en_sequence(pid, oid, days_ago=1)
    from envoi import sequence_engine as seq
    res = seq.send_relance(oid, pid)
    assert res['success'] and res['statut'] == 'envoye' and res['step'] == 'relance_1'
    assert len(fake_gateway) == 1
    from database import prospects_repo
    p = prospects_repo.get_prospect(pid)
    assert p['statut'] == 'relance_1'
    events = [e['event_type'] for e in p['events']]
    assert 'relance_1' in events


def test_send_relance_max_touches_ferme_le_cycle(tmp_db, fake_gateway):
    oid = _objectif(validation_telegram=0, max_touches=1)
    _seed_template_step(oid, 1, delai_jours=0)
    pid = _prospect(oid)
    _to_en_sequence(pid, oid, days_ago=1)
    from envoi import sequence_engine as seq
    res = seq.send_relance(oid, pid)
    assert res['success'] is False and res['statut'] == 'cycle_termine'
    assert fake_gateway == []
    from database import prospects_repo
    p = prospects_repo.get_prospect(pid)
    assert p['statut'] == 'sans_reponse'


def test_send_relance_hors_statut(tmp_db, fake_gateway):
    oid = _objectif(validation_telegram=0)
    _seed_template_step(oid, 1, delai_jours=0)
    pid = _prospect(oid)  # statut 'qualifie'
    from envoi import sequence_engine as seq
    res = seq.send_relance(oid, pid)
    assert res['success'] is False and res['statut'] == 'pas_de_relance'
    assert fake_gateway == []


def test_send_relance_validation_telegram_puis_approbation(tmp_db, fake_gateway, fake_tg):
    oid = _objectif(validation_telegram=1)
    _seed_template_step(oid, 1, delai_jours=0)
    pid = _prospect(oid)
    _to_en_sequence(pid, oid, days_ago=1)
    from envoi import sequence_engine as seq
    res = seq.send_relance(oid, pid)
    assert res['success'] is False and res['statut'] == 'attente_approbation'
    assert fake_gateway == []
    from database import prospects_repo
    p = prospects_repo.get_prospect(pid)
    assert p['statut'] == 'en_sequence'  # pas de transition avant ✅
    ev = [e for e in p['events'] if e['event_type'] == 'validation_requete']
    assert ev and ev[0]['payload'].get('step') == 'relance_1'
    # ✅ cliqué → le poller approuve puis envoie
    from envoi import telegram_validation as tv
    store = fake_tg
    store['status'][tv.callback_id(pid)] = 'ok'
    res2 = seq.approve_and_send_initial(pid)
    assert res2['success'] and res2['step'] == 'relance_1'
    assert len(fake_gateway) == 1
    p2 = prospects_repo.get_prospect(pid)
    assert p2['statut'] == 'relance_1'


def test_run_relances_kill_switch_et_manuel(tmp_db, fake_gateway):
    oid = _objectif(validation_telegram=0)
    _seed_template_step(oid, 1, delai_jours=0)
    pid = _prospect(oid)
    _to_en_sequence(pid, oid, days_ago=1)
    from database import campagnes as campagnes_repo
    campagnes_repo.set_auto_send_enabled(False)
    from core.orchestration import run_relances
    res = run_relances()
    assert res['quoted'] == 'global_off' and res['runs'] == []
    assert fake_gateway == []
    res2 = run_relances(objectif_id=oid, manual=True)
    assert res2['total'] == 1
    assert res2['runs'][0]['details'][0]['statut'] == 'envoye'
    assert len(fake_gateway) == 1
    from database import prospects_repo
    assert prospects_repo.get_prospect(pid)['statut'] == 'relance_1'


def test_template_update_et_inactif_retire_des_dues(tmp_db, fake_gateway):
    oid = _objectif()
    tid = _seed_template_step(oid, 1, delai_jours=0)['id']
    pid = _prospect(oid)
    _to_en_sequence(pid, oid, days_ago=1)
    from envoi import template_registry
    # désactivé → plus éligible aux relances
    assert template_registry.update(tid, actif=False)['success'] is True
    from core.orchestration import relances_due
    assert relances_due(oid) == []
    # réactivé + délai modifié → de nouveau due (delai 0)
    assert template_registry.update(tid, actif=True, delai_jours=0)['success'] is True
    assert [d['id'] for d in relances_due(oid)] == [pid]
    # update sur id inconnu → erreur
    assert template_registry.update(99999, actif=True)['success'] is False
    # update sans champ → erreur
    assert template_registry.update(tid)['success'] is False


def _relances_due_at(oid, now):
    from core.orchestration import relances_due
    return {d['id'] for d in relances_due(oid, now=now)}


def test_relances_due_exclut_weekend(tmp_db, fake_gateway):
    """Samedi/dimanche : aucune relance retenue, même si l'échéance est dépassée."""
    from datetime import datetime
    oid = _objectif(validation_telegram=0)
    _seed_template_step(oid, 1, delai_jours=0)
    pid = _prospect(oid)
    # touche initiale lundi 21/09/2026 09:00 → relance due dès lundi (delai 0)
    _to_en_sequence_at(pid, oid, '2026-09-21 09:00:00')
    sat = datetime(2026, 9, 19, 10, 0, 0)   # samedi
    sun = datetime(2026, 9, 20, 10, 0, 0)   # dimanche
    assert _relances_due_at(oid, sat) == set()
    assert _relances_due_at(oid, sun) == set()
    # weekdays suivants (lundi) : de nouveau éligible
    mon = datetime(2026, 9, 21, 11, 0, 0)
    assert pid in _relances_due_at(oid, mon)


def test_relances_due_echance_weekend_reportee_lundi(tmp_db, fake_gateway):
    """Échéance qui tombe samedi/dimanche → reportée au lundi suivant."""
    from datetime import datetime
    oid = _objectif(validation_telegram=0)
    _seed_template_step(oid, 1, delai_jours=2)
    pid = _prospect(oid)
    # touche jeudi 17/09 + 2 jours → échéance samedi 19/09 → effective lundi 21/09
    _to_en_sequence_at(pid, oid, '2026-09-17 09:00:00')
    fri = datetime(2026, 9, 18, 23, 0, 0)   # vendredi soir : pas encore (échéance w-e)
    assert _relances_due_at(oid, fri) == set()
    sat = datetime(2026, 9, 19, 10, 0, 0)
    assert _relances_due_at(oid, sat) == set()
    mon = datetime(2026, 9, 21, 10, 30, 0)  # lundi après report → due
    assert pid in _relances_due_at(oid, mon)


def test_relances_due_weekday_nominal_inchange(tmp_db, fake_gateway):
    """Régression : un délai purement ouvré reste éligible au jour prévu."""
    from datetime import datetime
    oid = _objectif(validation_telegram=0)
    _seed_template_step(oid, 1, delai_jours=2)
    pid = _prospect(oid)
    _to_en_sequence_at(pid, oid, '2026-09-21 09:00:00')  # lundi
    wed = datetime(2026, 9, 23, 10, 0, 0)   # mercredi 23/09 : 2 jours → due
    assert pid in _relances_due_at(oid, wed)
    tue = datetime(2026, 9, 22, 10, 0, 0)   # mardi : pas encore
    assert _relances_due_at(oid, tue) == set()