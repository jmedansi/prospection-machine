# -*- coding: utf-8 -*-
"""
Tests v2 — modèle piloté par objectif (schema v2, repos, machine à états, API).

Chaque test utilise une base SQLite temporaire : `database.connection.DB_PATH`
est redirigé vers un fichier de test. Aucune donnée de production n'est touchée.
"""
import pytest
from pathlib import Path

import database.connection as conn_mod
from database.schema import init_db, migrate_db


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "prospection_test.db"
    monkeypatch.setattr(conn_mod, 'DB_PATH', db_path)
    monkeypatch.setattr('database.schema.connection.DB_PATH', db_path)
    init_db()
    migrate_db()
    yield db_path


@pytest.fixture()
def client(tmp_db):
    from flask import Flask
    from dashboard.routes.objectifs import objectifs_bp
    app = Flask(__name__)
    app.testing = True
    app.register_blueprint(objectifs_bp)
    return app.test_client()


# ─── Repos : objectifs ─────────────────────────────────────────────────────────

def test_create_objectif_unique(tmp_db):
    from database import objectifs_repo
    r = objectifs_repo.create_objectif('Refonte site web', description='Commerces locaux')
    assert r['success']
    assert r['objectif']['nom'] == 'Refonte site web'
    dup = objectifs_repo.create_objectif('Refonte site web')
    assert not dup['success']
    missing = objectifs_repo.create_objectif('   ')
    assert not missing['success']


def test_update_and_archive_objectif(tmp_db):
    from database import objectifs_repo
    oid = objectifs_repo.create_objectif('Application scolaire')['objectif']['id']
    r = objectifs_repo.update_objectif(oid, validation_telegram=True, max_touches=4)
    assert r['success']
    assert r['objectif']['validation_telegram'] == 1
    assert r['objectif']['max_touches'] == 4
    objectifs_repo.update_objectif(oid, statut='archive')
    active = objectifs_repo.list_objectifs()
    assert oid not in [o['id'] for o in active]


# ─── Repos : prospects ─────────────────────────────────────────────────────────

def test_bulk_import_dedupe_and_stats(tmp_db):
    from database import objectifs_repo, prospects_repo
    oid = objectifs_repo.create_objectif('Refonte web')['objectif']['id']
    rows = [
        {'nom': 'Boulangerie Dupont', 'email': 'contact@dupont.fr', 'ville': 'Cotonou', 'secteur': 'boulangerie'},
        {'nom': 'Coiffure Aïcha', 'email': 'Aicha@Test.com', 'ville': 'Paris'},
        {'nom': 'Doublon', 'email': 'aicha@test.com', 'ville': 'Lyon'},
    ]
    s = prospects_repo.bulk_import(oid, rows, source='csv')
    assert s['importes'] == 2
    assert s['doublons'] == 1
    assert s['supprimes'] == 0
    lst = prospects_repo.list_prospects(oid, limit=10)
    assert lst['total'] == 2
    obj = objectifs_repo.list_objectifs()
    assert obj[0]['nb_leads'] == 2
    assert obj[0]['statut_breakdown'].get('qualifie') == 2


def test_suppression_list_globale_rejette_import(tmp_db):
    from database import objectifs_repo, prospects_repo
    oid1 = objectifs_repo.create_objectif('Objectif A')['objectif']['id']
    oid2 = objectifs_repo.create_objectif('Objectif B')['objectif']['id']
    prospects_repo.bulk_import(oid1, [{'nom': 'Jean', 'email': 'jean@test.fr'}])
    p = prospects_repo.list_prospects(oid1)['leads'][0]
    # désinscription -> alim suppression list globale
    prospects_repo.set_ne_plus_contacter(p['id'], True)
    # le même email est rejeté DANS un AUTRE objectif (list compte partout)
    s = prospects_repo.bulk_import(oid2, [{'nom': 'Jean bis', 'email': 'jean@test.fr'}])
    assert s['supprimes'] == 1
    assert s['importes'] == 0


def test_insert_prospect_sans_email_valide(tmp_db):
    from database import objectifs_repo, prospects_repo
    oid = objectifs_repo.create_objectif('Obj')['objectif']['id']
    r = prospects_repo.insert_prospect(oid, nom='Prospect sans email')
    assert r['success']
    r2 = prospects_repo.insert_prospect(oid, nom='')
    assert not r2['success']


# ─── Machine à états ───────────────────────────────────────────────────────────

def test_transitions_valides_et_invalides(tmp_db):
    from database import objectifs_repo, prospects_repo
    from core.state_machine import transition_prospect
    oid = objectifs_repo.create_objectif('Cible')['objectif']['id']
    pid = prospects_repo.insert_prospect(oid, nom='X', email='x@x.fr')['prospect_id']

    assert transition_prospect(pid, 'en_sequence')['success']
    assert transition_prospect(pid, 'relance_1')['success']
    assert transition_prospect(pid, 'relance_2')['success']
    # depuis relance_2, RDV direct interdit
    assert not transition_prospect(pid, 'rdv_obtenu')['success']
    # une réponse -> file humaine (suspend les relances)
    assert transition_prospect(pid, 'a_traiter_humain')['success']
    assert transition_prospect(pid, 'rdv_obtenu')['success']
    # les overrides transactionnels restent possibles depuis n'importe quel état
    assert transition_prospect(pid, 'ne_plus_contacter')['success']
    # l'état final ne bouge plus
    assert not transition_prospect(pid, 'a_traiter_humain')['success']


def test_evenement_journalise_statut(tmp_db):
    from database import objectifs_repo, prospects_repo
    from core.state_machine import transition_prospect
    oid = objectifs_repo.create_objectif('Obj')['objectif']['id']
    pid = prospects_repo.insert_prospect(oid, nom='Y', email='y@y.fr')['prospect_id']
    transition_prospect(pid, 'en_sequence', reason='initial')
    detail = prospects_repo.get_prospect(pid)
    types = [e['event_type'] for e in detail['events']]
    assert 'creation' in types
    assert 'status_change' in types
    assert detail['statut_meta']['previous_statut'] == 'qualifie'


# ─── API v2 ────────────────────────────────────────────────────────────────────

def test_api_crud_objectif(client):
    r = client.post('/api/v2/objectifs', json={'nom': 'Refonte site web'})
    assert r.status_code == 201
    oid = r.get_json()['objectif']['id']

    r = client.get('/api/v2/objectifs')
    assert r.status_code == 200
    assert len(r.get_json()['objectifs']) == 1

    r = client.put(f'/api/v2/objectifs/{oid}', json={'validation_telegram': True})
    assert r.status_code == 200
    assert r.get_json()['objectif']['validation_telegram'] == 1

    r = client.delete(f'/api/v2/objectifs/{oid}')
    assert r.status_code == 200
    r = client.get('/api/v2/objectifs')
    assert r.get_json()['objectifs'] == []


def test_api_import_csv(client):
    client.post('/api/v2/objectifs', json={'nom': 'Immobilier'})
    oid = client.get('/api/v2/objectifs').get_json()['objectifs'][0]['id']
    csv_text = ("nom,email,ville,secteur\n"
                "Agence Horizon,contact@horizon.fr,Paris,immobilier\n"
                "Cabinet Meridiem,km@meridiem.fr,Lyon,courtage\n")
    r = client.post(f'/api/v2/objectifs/{oid}/leads/import', data=csv_text, content_type='text/csv')
    d = r.get_json()
    assert d['success']
    assert d['importes'] == 2

    r = client.get(f'/api/v2/objectifs/{oid}/leads?limit=10')
    assert r.get_json()['total'] == 2


def test_api_import_json_et_chemin_obligatoire(client):
    client.post('/api/v2/objectifs', json={'nom': 'Écoles'})
    oid = client.get('/api/v2/objectifs').get_json()['objectifs'][0]['id']
    r = client.post(f'/api/v2/objectifs/{oid}/leads/import', json={'rows': [
        {'nom': 'Collège Lumière', 'email': 'c@lum.fr', 'ville': 'Nice'},
    ]})
    assert r.get_json()['importes'] == 1

    # un objectif inexistant -> 404, jamais d'import "orphelin" sans objectif
    r = client.post('/api/v2/objectifs/999999/leads/import', json={'rows': [{'nom': 'X'}]})
    assert r.status_code == 404


def test_api_transition_et_desinscription(client):
    client.post('/api/v2/objectifs', json={'nom': 'Cliniques'})
    oid = client.get('/api/v2/objectifs').get_json()['objectifs'][0]['id']
    client.post(f'/api/v2/objectifs/{oid}/leads', json={'nom': 'Clinique A', 'email': 'a@clinic.fr'})
    pid = client.get(f'/api/v2/objectifs/{oid}/leads').get_json()['leads'][0]['id']

    r = client.put(f'/api/v2/leads/{pid}/statut', json={'statut': 'en_sequence'})
    assert r.status_code == 200
    assert r.get_json()['statut'] == 'en_sequence'

    r = client.post(f'/api/v2/leads/{pid}/desinscrire', json={'ne_plus_contacter': True})
    assert r.status_code == 200
    detail = client.get(f'/api/v2/leads/{pid}').get_json()['lead']
    assert detail['ne_plus_contacter'] == 1
    assert detail['statut'] == 'ne_plus_contacter'  # spec §2 : transition d'état + opposition

    # l'email désinscrit n'est plus importable nulle part
    client.post('/api/v2/objectifs', json={'nom': 'Autre'})
    oid2 = client.get('/api/v2/objectifs').get_json()['objectifs'][-1]['id']
    r = client.post(f'/api/v2/objectifs/{oid2}/leads/import', json={'rows': [
        {'nom': 'Rebis', 'email': 'a@clinic.fr'},
    ]})
    assert r.get_json()['supprimes'] == 1


# ─── Registre d'ingestion (scraping → objectif v2) ─────────────────────────────

def test_resolve_or_create_objectif(tmp_db):
    from core.objectif_registry import resolve_or_create_objectif
    # création à la volée par nom
    res = resolve_or_create_objectif('Portails aluminium')
    assert res is not None
    oid, nom = res
    assert nom == 'Portails aluminium'
    # retrouvé au 2e appel (pas de création de doublon)
    res2 = resolve_or_create_objectif('Portails aluminium')
    assert res2 == (oid, 'Portails aluminium')
    # résolution par id numérique
    res3 = resolve_or_create_objectif(str(oid))
    assert res3 == (oid, 'Portails aluminium')
    # vide / introuvable
    assert resolve_or_create_objectif('') is None
    assert resolve_or_create_objectif(None) is None


def test_import_lead_as_prospect_mapping(tmp_db):
    from database import objectifs_repo, prospects_repo
    from core.objectif_registry import resolve_or_create_objectif, import_lead_as_prospect
    oid, _ = resolve_or_create_objectif('Scraping Bénin')
    lead = {
        'nom': 'Boulangerie Dupont', 'adresse': 'Quartier Akpakpa',
        'site_web': 'https://dupont.bj', 'telephone': '+22997000000',
        'rating': 4.5, 'nb_avis': 120, 'logo_url': 'https://x/logo.png',
        'email': 'contact@dupont.bj', 'email_2': 'dir@dupont.bj',
        'statut_email': 'Valide', 'email_source': 'site_web',
        'date_scraping': '2026-01-01 10:00:00', 'mot_cle': 'boulangerie',
        'ville': 'Cotonou', 'category': 'Boulangerie', 'lien_maps': 'https://maps/1',
        'campaign_id': 7, 'pays': 'bj',
    }
    r = import_lead_as_prospect(oid, lead, source='scraping', data_extra_extra={'campaign_id': 7})
    assert r['success']
    assert r['statut_dedupe'] == 'created'

    p = prospects_repo.list_prospects(oid)['leads'][0]
    assert p['nom'] == 'Boulangerie Dupont'
    assert p['email'] == 'contact@dupont.bj'
    assert p['telephone'] == '+22997000000'
    assert p['site_web'] == 'https://dupont.bj'
    assert p['secteur'] == 'Boulangerie'  # category → secteur
    assert p['source'] == 'scraping'
    xe = p['data_extra']
    assert xe['lien_maps'] == 'https://maps/1'
    assert xe['logo_url'] == 'https://x/logo.png'
    assert xe['email_2'] == 'dir@dupont.bj'
    assert xe['campaign_id'] == 7
    assert xe['pays'] == 'bj'

    # re-scrap même email → doublon dans l'objectif
    r2 = import_lead_as_prospect(oid, lead, source='scraping')
    assert r2['statut_dedupe'] == 'doublon'


def test_import_lead_rejete_suppression_liste(tmp_db):
    from database import objectifs_repo, prospects_repo
    from core.objectif_registry import resolve_or_create_objectif, import_lead_as_prospect
    oid, _ = resolve_or_create_objectif('Cible')
    row = {'nom': 'Sans Email'}
    # un lead avec nom ET email pour déclencher la désinscription
    r = import_lead_as_prospect(oid, {'nom': 'Opt-out SARL', 'email': 'no@optout.fr'})
    assert r['success']
    pid = r['prospect_id']
    prospects_repo.set_ne_plus_contacter(pid, True)
    # nouveau scraping du même email → suppression_list (refus global)
    r2 = import_lead_as_prospect(oid, {'nom': 'Opt-out (rescrape)', 'email': 'no@optout.fr'})
    assert r2['statut_dedupe'] == 'suppression_list'


def test_import_lead_sans_nom_ni_email(tmp_db):
    from core.objectif_registry import resolve_or_create_objectif, import_lead_as_prospect
    oid, _ = resolve_or_create_objectif('Vide')
    r = import_lead_as_prospect(oid, {'nom': '', 'email': ''})
    assert not r['success']


# ─── Séquence & relances (routes) ─────────────────────────────────────────────

def test_transitions_endpoint(client):
    d = client.get('/api/v2/statuts/transitions').get_json()
    assert d['success']
    assert 'a_traiter_humain' in d['transitions']
    # file humaine : depuis a_traiter_humain on peut clôturer en rdv / pas intéressé
    assert 'rdv_obtenu' in d['transitions']['a_traiter_humain']
    assert 'pas_interesse' in d['transitions']['a_traiter_humain']
    assert 'a_relancer_plus_tard' in d['transitions']['a_traiter_humain']
    # état final : aucune transition
    assert d['transitions']['rdv_obtenu'] == []
    assert d['labels']['a_traiter_humain'] == 'À traiter'


def test_lead_detail_events(client):
    o = client.post('/api/v2/objectifs', json={'nom': 'Objectif detail'}).get_json()['objectif']
    res = client.post(f'/api/v2/objectifs/{o["id"]}/leads', json={'nom': 'Cible', 'email': 'cible@exemple.fr'}).get_json()
    pid = res['prospect_id']
    d = client.get(f'/api/v2/leads/{pid}').get_json()['lead']
    assert d['email'] == 'cible@exemple.fr'
    assert d['objectif_nom'] == 'Objectif detail'
    assert any(e['event_type'] == 'creation' for e in d['events'])
    # 404
    assert client.get('/api/v2/leads/999999').get_json()['success'] is False


def test_sequence_routes_crud(client):
    from database import objectifs_repo
    oid = objectifs_repo.create_objectif('Séquence web')['objectif']['id']

    # liste vide au départ (aucune étape dédiée)
    r = client.get(f'/api/v2/objectifs/{oid}/sequence')
    assert r.status_code == 200
    data = r.get_json()
    assert data['success']
    assert data['templates'] == [] or all(t['objectif_id'] != oid for t in data['templates'])

    # ajout d'une étape (relance 1, délai 3j)
    r = client.post(f'/api/v2/objectifs/{oid}/sequence', json={
        'position': 1, 'delai_jours': 3, 'objet': 'Re: {{prenom}}', 'corps': 'Bonjour {{prenom}}',
    })
    assert r.status_code == 201
    tid = r.get_json()['id']
    assert tid

    # la liste contient maintenant l'étape dédiée
    r = client.get(f'/api/v2/objectifs/{oid}/sequence')
    tpl = [t for t in r.get_json()['templates'] if t['id'] == tid]
    assert tpl and tpl[0]['delai_jours'] == 3 and tpl[0]['position'] == 1

    # update (delai + inactif)
    r = client.put(f'/api/v2/sequence-templates/{tid}', json={'delai_jours': 7, 'actif': False})
    assert r.status_code == 200 and r.get_json()['success']
    r = client.get(f'/api/v2/objectifs/{oid}/sequence')
    tpl = [t for t in r.get_json()['templates'] if t['id'] == tid]
    assert tpl[0]['delai_jours'] == 7 and tpl[0]['actif'] == 0

    # update sur template inconnu → 404
    r = client.put('/api/v2/sequence-templates/999999', json={'delai_jours': 1})
    assert r.status_code == 404

    # suppression
    r = client.delete(f'/api/v2/sequence-templates/{tid}')
    assert r.status_code == 200
    r = client.get(f'/api/v2/objectifs/{oid}/sequence')
    assert all(t['id'] != tid for t in r.get_json()['templates'])

    # objectif inconnu → 404
    r = client.get('/api/v2/objectifs/999999/sequence')
    assert r.status_code == 404