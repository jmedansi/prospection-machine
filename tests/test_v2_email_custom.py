# -*- coding: utf-8 -*-
"""
tests/test_v2_email_custom.py — régression : emails personnalisés (modèles rédigés
agent IA / utilisateur) sans template de séquence.

Le bug corrigé : `prepare_step` renvoie `template=None` quand un email personnalisé
existe (`data_extra.email_corps`), et `send_initial`/`send_relance` plantaient sur
`prep['template'].get('id')` (AttributeError 'NoneType' — observable dans errors.log à
l'étape position 0). Ce test garantit qu'un envoi personnalisé ne lève plus et aboutit.
"""
import pytest

from database import connection as conn_mod


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test_custom.db")
    monkeypatch.setattr(conn_mod, 'DB_PATH', db_path)
    monkeypatch.setattr('database.schema.connection.DB_PATH', db_path)
    from database import schema
    schema.init_db()
    schema.migrate_v2_schema()
    yield db_path


def _campagne(nom='Campagne custom'):
    from core.objectif_registry import resolve_or_create_campagne
    oid, _ = resolve_or_create_campagne(nom)
    return oid


def _prospect(oid, extra=None, statut='qualifie'):
    from core.objectif_registry import get_or_create_liste
    from database import prospects_repo
    lid = get_or_create_liste(oid)
    data_extra = {
        'email_objet': 'Ma proposition pour {{entreprise}}',
        'email_corps': 'Bonjour {{prenom}},\n\nVoici ma proposition.',
        **(extra or {}),
    }
    return prospects_repo.insert_prospect(lid, nom='Boulangerie Dupont', email='dupont@mail.fr',
                                          prenom='M. Dupont', entreprise='Boulangerie Dupont',
                                          secteur='Boulangerie', data_extra=data_extra)['prospect_id']


@pytest.fixture
def fake_gateway(monkeypatch):
    calls = []

    def _envoyer(message, boite=None):
        calls.append(dict(message))
        return {'success': True, 'statut': 'envoye', 'message_id': 'msg-custom',
                'boite': {'id': 9, 'email': 'boite@test.fr', 'backend': 'smtp'}}

    monkeypatch.setattr('envoi.sequence_engine.gateway.envoyer', _envoyer)
    return calls


def test_send_initial_custom_sans_template_neq_crash(tmp_db, fake_gateway):
    """Pas de template position 0 : l'email personnalisé suffit (régression crash)."""
    oid = _campagne()
    pid = _prospect(oid)  # data_extra.email_corps → template reste None
    from envoi import sequence_engine as seq
    res = seq.send_initial(oid, pid)  # plantait sur prep['template'].get('id')
    assert res['success'] is True
    assert res['statut'] == 'envoye' and res['step'] == 'initial'
    assert len(fake_gateway) == 1


def test_send_relance_custom_pos1_sans_template_neq_crash(tmp_db, fake_gateway):
    """Pas de template position 1 : email personnalisé de relance (email_corps_2)."""
    oid = _campagne()
    pid = _prospect(oid, extra={'email_objet_2': 'Relance: ma proposition',
                                'email_corps_2': 'Bonjour {{prenom}},\n\nRelance.'})
    from database import prospects_repo
    from core.state_machine import transition_prospect
    transition_prospect(pid, 'en_sequence', reason='initial (test)')
    from envoi import sequence_engine as seq
    res = seq.send_relance(oid, pid)  # plantait sur prep['template'].get('id')
    assert res['success'] is True
    assert res['statut'] == 'envoye' and res['step'] == 'relance_1'
    assert len(fake_gateway) == 1
    event = [e for e in prospects_repo.get_prospect(pid)['events'] if e['event_type'] == 'relance_1']
    assert event and event[0]['payload'].get('template_id') is None


def test_send_initial_sans_email_ni_template_pas_template(tmp_db, fake_gateway):
    """Ni email personnalisé ni template de séquence → verrou pas_template (pas de crash)."""
    oid = _campagne()
    from database import prospects_repo
    from core.objectif_registry import get_or_create_liste
    from database.connection import get_conn
    lid = get_or_create_liste(oid)
    pid = prospects_repo.insert_prospect(
        lid, nom='X', email='x@mail.fr', entreprise='X',
        data_extra={'note': 'rien'},  # pas d'email_corps
    )['prospect_id']
    # Le seed migrate_v2_schema crée un template générique position 0 → on le retire
    with get_conn() as c:
        c.execute("DELETE FROM sequence_templates")
        c.commit()
    from envoi import sequence_engine as seq
    res = seq.send_initial(oid, pid)
    assert res['success'] is False
    assert res['statut'] == 'pas_template'
    assert fake_gateway == []