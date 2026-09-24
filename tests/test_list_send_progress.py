# -*- coding: utf-8 -*-
"""
tests/test_list_send_progress.py — Tests d'isolation d'envoi par liste, de progression temps réel et de tracking.
"""
import time
import pytest
from database import connection as conn_mod


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test_prospection_lists.db")
    monkeypatch.setattr(conn_mod, 'DB_PATH', db_path)
    monkeypatch.setattr('database.schema.connection.DB_PATH', db_path)
    monkeypatch.setattr('core.orchestration._pause_humain', lambda *a, **k: None)
    monkeypatch.setenv('PROSPECTION_DELAY_MIN', '0')
    monkeypatch.setenv('PROSPECTION_DELAY_MAX', '0')
    from database import schema
    schema.init_db()
    schema.migrate_v2_schema()
    yield db_path


@pytest.fixture
def fake_gateway(monkeypatch):
    calls = []

    def _envoyer(message, boite=None):
        calls.append(dict(message))
        return {'success': True, 'statut': 'envoye', 'message_id': '<msg-test-123@prospection.fr>',
                'boite': {'id': 1, 'email': 'sender@test.fr', 'backend': 'smtp'}}

    from envoi import gateway as gw
    monkeypatch.setattr(gw, 'envoyer', _envoyer)
    monkeypatch.setattr('envoi.sequence_engine.gateway.envoyer', _envoyer)
    return calls


def _create_campagne_and_lists():
    from core.objectif_registry import resolve_or_create_campagne
    from database import listes as listes_repo
    from database import prospects as prospects_repo
    from database.connection import get_conn

    cid, _ = resolve_or_create_campagne('Campagne Multi-Listes')
    with get_conn() as c:
        c.execute("UPDATE campagnes SET envoi_auto=1, validation_telegram=0 WHERE id=?", (cid,))
        c.commit()

    # Créer Liste 1
    l1 = listes_repo.create_liste(cid, nom='Liste Boulangeries', secteur='Boulangerie')
    l1_id = l1['liste']['id']

    # Créer Liste 2
    l2 = listes_repo.create_liste(cid, nom='Liste Fleuristes', secteur='Fleuriste')
    l2_id = l2['liste']['id']

    # 3 prospects dans Liste 1
    ia = {'email_objet': 'Une proposition pour {{entreprise}}',
          'email_corps': 'Bonjour,\n\nVoici ma proposition.'}  # source de vérité v2
    p1 = prospects_repo.insert_prospect(l1_id, nom='Boulangerie A', email='a@boulangerie.fr', data_extra=ia)['prospect_id']
    p2 = prospects_repo.insert_prospect(l1_id, nom='Boulangerie B', email='b@boulangerie.fr', data_extra=ia)['prospect_id']
    p3 = prospects_repo.insert_prospect(l1_id, nom='Boulangerie C', email='c@boulangerie.fr', data_extra=ia)['prospect_id']

    # 2 prospects dans Liste 2
    p4 = prospects_repo.insert_prospect(l2_id, nom='Fleurs D', email='d@fleurs.fr', data_extra=ia)['prospect_id']
    p5 = prospects_repo.insert_prospect(l2_id, nom='Fleurs E', email='e@fleurs.fr', data_extra=ia)['prospect_id']

    return {
        'campagne_id': cid,
        'liste_1_id': l1_id,
        'liste_2_id': l2_id,
        'prospects_1': [p1, p2, p3],
        'prospects_2': [p4, p5],
    }


def test_list_send_isolation_strictly_targets_one_list(tmp_db, fake_gateway):
    """Vérifie que l'envoi de la Liste 1 n'envoie que les prospects de la Liste 1."""
    data = _create_campagne_and_lists()
    cid = data['campagne_id']
    l1_id = data['liste_1_id']
    l2_id = data['liste_2_id']

    from core.orchestration import candidates_for, run_auto_send
    from database import prospects as prospects_repo

    # Vérifier que candidates_for filtre bien par liste
    cands_l1 = candidates_for(cid, liste_id=l1_id)
    assert len(cands_l1) == 3
    assert {c['id'] for c in cands_l1} == set(data['prospects_1'])

    cands_l2 = candidates_for(cid, liste_id=l2_id)
    assert len(cands_l2) == 2
    assert {c['id'] for c in cands_l2} == set(data['prospects_2'])

    # Envoi de la Liste 1 uniquement
    progress_calls = []
    def _on_prog(cur, tot, cand, res):
        progress_calls.append((cur, tot, cand.get('id'), res.get('statut')))

    res = run_auto_send(cid, manual=True, liste_id=l1_id, progress_callback=_on_prog)
    assert res['success'] is True
    assert res['total'] == 3

    # Vérifier que les 3 callbacks ont été déclenchés
    assert len(progress_calls) == 3
    assert progress_calls[0][0] == 1 and progress_calls[0][1] == 3
    assert progress_calls[2][0] == 3 and progress_calls[2][1] == 3

    # Vérifier les statuts des prospects de Liste 1 -> en_sequence
    for pid in data['prospects_1']:
        lead = prospects_repo.get_prospect(pid)
        assert lead['statut'] == 'en_sequence'

    # Vérifier que les prospects de Liste 2 sont RESTÉS qualifie (non envoyés)
    for pid in data['prospects_2']:
        lead = prospects_repo.get_prospect(pid)
        assert lead['statut'] == 'qualifie'

    assert len(fake_gateway) == 3


def test_tracking_link_and_pixel_injection(tmp_db):
    """Vérifie que le tracking maison injecte le pixel et réécrit les liens."""
    from envoi import track_links

    assert track_links.tracking_enabled() is True
    base_url = track_links.get_base_url()
    assert base_url.startswith('http')

    sample_html = '<p>Bonjour, découvrez notre offre : <a href="https://example.com/demo">Voir la démo</a></p></body>'
    mid = '<msg-12345@test.fr>'
    tracked_html = track_links.apply_tracking(sample_html, mid)

    # Vérifier le lien réécrit
    assert '/api/webhooks/track/click/' in tracked_html
    assert 'https%3A%2F%2Fexample.com%2Fdemo' in tracked_html

    # Vérifier le pixel
    assert '/api/webhooks/track/pixel/' in tracked_html
    assert 'msg-12345' in tracked_html


def test_api_list_send_and_status(tmp_db, fake_gateway):
    """Vérifie les endpoints /api/v2/listes/<id>/send et /send/status."""
    data = _create_campagne_and_lists()
    l1_id = data['liste_1_id']

    from dashboard.app import create_app
    app = create_app()
    client = app.test_client()

    # Appel POST pour lancer l'envoi de la liste
    resp = client.post(f'/api/v2/listes/{l1_id}/send', json={})
    assert resp.status_code == 200
    res_data = resp.get_json()
    assert res_data['success'] is True
    assert res_data['total'] == 3
    job_id = res_data.get('job_id')
    assert job_id is not None

    # Attendre que le thread s'exécute
    time.sleep(0.5)

    # Vérifier le statut
    status_resp = client.get(f'/api/v2/listes/{l1_id}/send/status')
    assert status_resp.status_code == 200
    status_data = status_resp.get_json()
    assert status_data['success'] is True
    job = status_data['job']
    assert job['liste_id'] == l1_id
    assert job['total'] == 3


def test_candidates_for_prospect_ids_selection_filter(tmp_db, fake_gateway):
    """Vérifie que candidates_for/relances_due restreignent à une sélection (lead_ids)."""
    data = _create_campagne_and_lists()
    cid = data['campagne_id']
    l1_id = data['liste_1_id']
    p1, p2, p3 = data['prospects_1']

    from core.orchestration import candidates_for, relances_due

    # Sélection d'un seul prospect
    sel = candidates_for(cid, limit=None, liste_id=l1_id, prospect_ids=[p2])
    assert [c['id'] for c in sel] == [p2]

    # Sélection de deux prospects (ordre FIFO conservé)
    sel2 = candidates_for(cid, limit=None, liste_id=l1_id, prospect_ids=[p3, p1])
    assert [c['id'] for c in sel2] == [p1, p3]

    # Prospect absent de la liste → exclu
    sel3 = candidates_for(cid, limit=None, liste_id=l1_id, prospect_ids=[p2, 999999])
    assert [c['id'] for c in sel3] == [p2]

    # IDs inexistants → aucun candidat
    assert candidates_for(cid, limit=None, liste_id=l1_id, prospect_ids=[999999]) == []

    # prospect_ids=None → tous les éligibles (comportement legacy)
    assert len(candidates_for(cid, limit=None, liste_id=l1_id)) == 3

    # relances_due : la sélection est ignorée tant qu'aucune relance n'est due
    assert relances_due(cid, liste_id=l1_id, prospect_ids=[p1]) == []


def test_api_send_list_with_lead_ids_selection(tmp_db, fake_gateway):
    """L'envoi d'une liste avec lead_ids ne cible que les prospects sélectionnés."""
    data = _create_campagne_and_lists()
    l1_id = data['liste_1_id']
    p1, p2, p3 = data['prospects_1']

    from dashboard.app import create_app
    app = create_app()
    client = app.test_client()

    resp = client.post(f'/api/v2/listes/{l1_id}/send', json={'lead_ids': [p2]})
    assert resp.status_code == 200
    res_data = resp.get_json()
    assert res_data['success'] is True
    assert res_data['total'] == 1

    from database import prospects as prospects_repo
    time.sleep(0.5)
    # Seul p2 est passé en en_sequence ; les autres restent qualifie
    assert prospects_repo.get_prospect(p2)['statut'] == 'en_sequence'
    assert prospects_repo.get_prospect(p1)['statut'] == 'qualifie'
    assert prospects_repo.get_prospect(p3)['statut'] == 'qualifie'


def test_api_bulk_ecarter_et_desinscrire(tmp_db, fake_gateway):
    """Endpoints bulk : écarter / désinscrire / supprimer une sélection en un appel."""
    data = _create_campagne_and_lists()
    p1, p2, p3 = data['prospects_1']

    from dashboard.app import create_app
    app = create_app()
    client = app.test_client()
    from database import prospects as prospects_repo

    # Écarter la sélection [p1, p3]
    resp = client.post('/api/v2/leads/bulk/ecarter', json={'lead_ids': [p1, p3], 'ecarte': True})
    assert resp.status_code == 200
    assert resp.get_json()['updated'] == 2
    assert prospects_repo.get_prospect(p1)['ecarte'] == 1
    assert prospects_repo.get_prospect(p2)['ecarte'] == 0
    assert prospects_repo.get_prospect(p3)['ecarte'] == 1

    # Réintégrer p1 seul
    resp = client.post('/api/v2/leads/bulk/ecarter', json={'lead_ids': [p1], 'ecarte': False})
    assert resp.get_json()['updated'] == 1
    assert prospects_repo.get_prospect(p1)['ecarte'] == 0

    # Désinscrire [p2]
    resp = client.post('/api/v2/leads/bulk/desinscrire', json={'lead_ids': [p2], 'ne_plus_contacter': True})
    assert resp.get_json()['updated'] == 1
    assert prospects_repo.get_prospect(p2)['ne_plus_contacter'] == 1

    # Suppression en masse [p1, p3]
    resp = client.delete('/api/v2/leads/bulk', json={'lead_ids': [p1, p3]})
    assert resp.status_code == 200
    assert resp.get_json()['deleted'] == 2
    assert prospects_repo.get_prospect(p1) is None
    assert prospects_repo.get_prospect(p3) is None

    # lead_ids vides → 400
    assert client.post('/api/v2/leads/bulk/ecarter', json={'lead_ids': []}).status_code == 400
