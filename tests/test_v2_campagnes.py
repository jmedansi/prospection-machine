# -*- coding: utf-8 -*-
"""
Tests v2 — modèle Campagne → Liste → Prospect (schema v2, repos, machine à états, API).

Chaque test utilise une base SQLite temporaire : `database.connection.DB_PATH`
est redirigé vers un fichier de test. Aucune donnée de production n'est touchée.
"""
import pytest

import database.connection as conn_mod
from database.schema import init_db, migrate_v2_schema


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "prospection_test.db"
    monkeypatch.setattr(conn_mod, 'DB_PATH', db_path)
    monkeypatch.setattr('database.schema.connection.DB_PATH', db_path)
    init_db()
    migrate_v2_schema()
    yield db_path


@pytest.fixture()
def client(tmp_db):
    from flask import Flask
    from dashboard.routes.campagnes import campagnes_bp
    from dashboard.routes.listes import listes_bp
    from dashboard.routes.objectifs import objectifs_bp
    app = Flask(__name__)
    app.testing = True
    app.register_blueprint(campagnes_bp)
    app.register_blueprint(listes_bp)
    app.register_blueprint(objectifs_bp)
    return app.test_client()


def _campagne(nom='Refonte site web', **kwargs):
    from database import campagnes_repo
    return campagnes_repo.create_campagne(nom, **kwargs)['campagne']['id']


def _prospect(cid, email='contact@dupont.fr'):
    from core.objectif_registry import get_or_create_liste
    from database import prospects_repo
    return prospects_repo.insert_prospect(
        get_or_create_liste(cid),
        nom='Boulangerie Dupont', email=email, entreprise='Boulangerie Dupont',
        secteur='Boulangerie')['prospect_id']

# ─── Repos : campagnes ─────────────────────────────────────────────────────────

def test_create_campagne_unique(tmp_db):
    from database import campagnes_repo
    r = campagnes_repo.create_campagne('Refonte site web', description='Commerces locaux')
    assert r['success']
    assert r['campagne']['nom'] == 'Refonte site web'
    dup = campagnes_repo.create_campagne('Refonte site web')
    assert not dup['success']
    missing = campagnes_repo.create_campagne('   ')
    assert not missing['success']


def test_create_campagne_auto_creer_liste(tmp_db):
    from database import campagnes_repo, listes_repo
    cid = _campagne('Portails')
    l = listes_repo.list_listes(campagne_id=cid)
    assert len(l) == 1
    assert l[0]['campagne_id'] == cid


def test_update_et_archive_campagne(tmp_db):
    from database import campagnes_repo
    cid = _campagne('Application scolaire')
    r = campagnes_repo.update_campagne(cid, validation_telegram=True, max_touches=4)
    assert r['success']
    assert r['campagne']['validation_telegram'] == 1
    assert r['campagne']['max_touches'] == 4
    campagnes_repo.update_campagne(cid, statut='archive')
    active = campagnes_repo.list_campagnes()
    assert cid not in [c['id'] for c in active]


# ─── Repos : prospects (dans liste d'une campagne) ─────────────────────────────

def test_bulk_import_dedupe_and_stats(tmp_db):
    from database import campagnes_repo, prospects_repo
    from core.objectif_registry import get_or_create_liste
    cid = _campagne('Refonte web')
    lid = get_or_create_liste(cid)
    rows = [
        {'nom': 'Boulangerie Dupont', 'email': 'contact@dupont.fr', 'ville': 'Cotonou', 'secteur': 'boulangerie'},
        {'nom': 'Coiffure Aïcha', 'email': 'Aicha@Test.com', 'ville': 'Paris'},
        {'nom': 'Doublon', 'email': 'aicha@test.com', 'ville': 'Lyon'},
    ]
    s = prospects_repo.bulk_import(lid, rows, source='csv')
    assert s['importes'] == 2
    assert s['doublons'] == 1
    assert s['supprimes'] == 0
    lst = prospects_repo.list_prospects(campagne_id=cid, limit=10)
    assert lst['total'] == 2
    camp = campagnes_repo.list_campagnes()
    assert camp[0]['nb_leads'] == 2
    assert camp[0]['statut_breakdown'].get('qualifie') == 2
    assert camp[0]['nb_listes'] == 1


def test_suppression_list_globale_rejette_import(tmp_db):
    from database import prospects_repo
    from core.objectif_registry import get_or_create_liste
    cid1 = _campagne('Campagne A')
    cid2 = _campagne('Campagne B')
    lid1 = get_or_create_liste(cid1)
    lid2 = get_or_create_liste(cid2)
    prospects_repo.bulk_import(lid1, [{'nom': 'Jean', 'email': 'jean@test.fr'}])
    p = prospects_repo.list_prospects(campagne_id=cid1)['leads'][0]
    prospects_repo.set_ne_plus_contacter(p['id'], True)
    # le même email rejeté DANS UNE AUTRE campagne (list compte partout)
    s = prospects_repo.bulk_import(lid2, [{'nom': 'Jean bis', 'email': 'jean@test.fr'}])
    assert s['supprimes'] == 1
    assert s['importes'] == 0


def test_insert_prospect_sans_email_valide(tmp_db):
    from database import prospects_repo
    from core.objectif_registry import get_or_create_liste
    cid = _campagne('Obj')
    lid = get_or_create_liste(cid)
    r = prospects_repo.insert_prospect(lid, nom='Prospect sans email')
    assert r['success']
    r2 = prospects_repo.insert_prospect(lid, nom='')
    assert not r2['success']


# ─── Machine à états ───────────────────────────────────────────────────────────

def test_transitions_valides_et_invalides(tmp_db):
    from database import prospects_repo
    from core.state_machine import transition_prospect
    cid = _campagne('Cible')
    pid = _prospect(cid, email='x@x.fr')

    assert transition_prospect(pid, 'en_sequence')['success']
    assert transition_prospect(pid, 'relance_1')['success']
    assert transition_prospect(pid, 'relance_2')['success']
    assert not transition_prospect(pid, 'rdv_obtenu')['success']
    assert transition_prospect(pid, 'a_traiter_humain')['success']
    assert transition_prospect(pid, 'rdv_obtenu')['success']
    assert transition_prospect(pid, 'ne_plus_contacter')['success']
    assert not transition_prospect(pid, 'a_traiter_humain')['success']


def test_evenement_journalise_statut(tmp_db):
    from database import prospects_repo
    from core.state_machine import transition_prospect
    cid = _campagne('Obj')
    pid = _prospect(cid, email='y@y.fr')
    transition_prospect(pid, 'en_sequence', reason='initial')
    detail = prospects_repo.get_prospect(pid)
    types = [e['event_type'] for e in detail['events']]
    assert 'creation' in types
    assert 'status_change' in types
    assert detail['statut_meta']['previous_statut'] == 'qualifie'


# ─── API v2 : campagnes ────────────────────────────────────────────────────────

def test_api_crud_campagne(client):
    r = client.post('/api/v2/campagnes', json={'nom': 'Refonte site web'})
    assert r.status_code == 201
    cid = r.get_json()['campagne']['id']

    r = client.get('/api/v2/campagnes')
    assert r.status_code == 200
    assert len(r.get_json()['campagnes']) == 1

    r = client.put(f'/api/v2/campagnes/{cid}', json={'validation_telegram': True})
    assert r.status_code == 200
    assert r.get_json()['campagne']['validation_telegram'] == 1

    r = client.delete(f'/api/v2/campagnes/{cid}')
    assert r.status_code == 200
    r = client.get('/api/v2/campagnes')
    assert r.get_json()['campagnes'] == []


def test_api_anciens_endpoints_objectifs_301(client):
    r = client.get('/api/v2/objectifs')
    assert r.status_code == 301
    assert '/api/v2/campagnes' in r.headers['Location']
    r2 = client.post('/api/v2/objectifs', json={'nom': 'X'})
    assert r2.status_code == 301


def test_api_import_csv(client):
    client.post('/api/v2/campagnes', json={'nom': 'Immobilier'})
    cid = client.get('/api/v2/campagnes').get_json()['campagnes'][0]['id']
    csv_text = ("nom,email,ville,secteur\n"
                "Agence Horizon,contact@horizon.fr,Paris,immobilier\n"
                "Cabinet Meridiem,km@meridiem.fr,Lyon,courtage\n")
    r = client.post(f'/api/v2/campagnes/{cid}/leads/import', data=csv_text, content_type='text/csv')
    d = r.get_json()
    assert d['success']
    assert d['importes'] == 2

    r = client.get(f'/api/v2/campagnes/{cid}/leads?limit=10')
    assert r.get_json()['total'] == 2


def test_api_import_json_et_chemin_obligatoire(client):
    client.post('/api/v2/campagnes', json={'nom': 'Écoles'})
    cid = client.get('/api/v2/campagnes').get_json()['campagnes'][0]['id']
    r = client.post(f'/api/v2/campagnes/{cid}/leads/import', json={'rows': [
        {'nom': 'Collège Lumière', 'email': 'c@lum.fr', 'ville': 'Nice'},
    ]})
    assert r.get_json()['importes'] == 1

    # campagne inexistante -> 404, jamais d'import "orphelin" sans campagne
    r = client.post('/api/v2/campagnes/999999/leads/import', json={'rows': [{'nom': 'X'}]})
    assert r.status_code == 404


def test_api_transition_et_desinscription(client):
    client.post('/api/v2/campagnes', json={'nom': 'Cliniques'})
    cid = client.get('/api/v2/campagnes').get_json()['campagnes'][0]['id']
    client.post(f'/api/v2/campagnes/{cid}/leads', json={'nom': 'Clinique A', 'email': 'a@clinic.fr'})
    pid = client.get(f'/api/v2/campagnes/{cid}/leads').get_json()['leads'][0]['id']

    r = client.put(f'/api/v2/leads/{pid}/statut', json={'statut': 'en_sequence'})
    assert r.status_code == 200
    assert r.get_json()['statut'] == 'en_sequence'

    r = client.post(f'/api/v2/leads/{pid}/desinscrire', json={'ne_plus_contacter': True})
    assert r.status_code == 200
    detail = client.get(f'/api/v2/leads/{pid}').get_json()['lead']
    assert detail['ne_plus_contacter'] == 1
    assert detail['statut'] == 'ne_plus_contacter'

    # l'email désinscrit n'est plus importable nulle part
    client.post('/api/v2/campagnes', json={'nom': 'Autre'})
    cid2 = client.get('/api/v2/campagnes').get_json()['campagnes'][-1]['id']
    r = client.post(f'/api/v2/campagnes/{cid2}/leads/import', json={'rows': [
        {'nom': 'Rebis', 'email': 'a@clinic.fr'},
    ]})
    assert r.get_json()['supprimes'] == 1


# ─── Registre d'ingestion (scraping → campagne v2) ─────────────────────────────

def test_resolve_or_create_campagne(tmp_db):
    from core.objectif_registry import resolve_or_create_campagne
    res = resolve_or_create_campagne('Portails aluminium')
    assert res is not None
    cid, nom = res
    assert nom == 'Portails aluminium'
    res2 = resolve_or_create_campagne('Portails aluminium')
    assert res2 == (cid, 'Portails aluminium')
    res3 = resolve_or_create_campagne(str(cid))
    assert res3 == (cid, 'Portails aluminium')
    assert resolve_or_create_campagne('') is None
    assert resolve_or_create_campagne(None) is None


def test_import_lead_as_prospect_mapping(tmp_db):
    from database import prospects_repo
    from core.objectif_registry import resolve_or_create_campagne, import_lead_as_prospect
    cid, _ = resolve_or_create_campagne('Scraping Bénin')
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
    r = import_lead_as_prospect(cid, lead, source='scraping', data_extra_extra={'campaign_id': 7})
    assert r['success']
    assert r['statut_dedupe'] == 'created'

    p = prospects_repo.list_prospects(campagne_id=cid)['leads'][0]
    assert p['nom'] == 'Boulangerie Dupont'
    assert p['email'] == 'contact@dupont.bj'
    assert p['telephone'] == '+22997000000'
    assert p['site_web'] == 'https://dupont.bj'
    assert p['secteur'] == 'Boulangerie'
    assert p['source'] == 'scraping'
    xe = p['data_extra']
    assert xe['lien_maps'] == 'https://maps/1'
    assert xe['logo_url'] == 'https://x/logo.png'
    assert xe['email_2'] == 'dir@dupont.bj'
    assert xe['campaign_id'] == 7
    assert xe['pays'] == 'bj'

    # re-scrap même email → doublon DANS la même liste
    r2 = import_lead_as_prospect(cid, lead, source='scraping')
    assert r2['statut_dedupe'] == 'doublon'


def test_dedup_site_et_tel_dans_campagne(tmp_db):
    from database import prospects_repo
    from core.objectif_registry import resolve_or_create_campagne, import_lead_as_prospect, get_or_create_liste
    cid, _ = resolve_or_create_campagne('Scraping Doublons')
    lid = get_or_create_liste(cid)

    # Même site_web (www/paramètres/trailing slash) mais email différent → doublon
    r1 = prospects_repo.insert_prospect(lid, nom='Resto A', email='a@resto.fr',
                                        site_web='https://www.monresto.fr/page?x=1')
    assert r1['statut_dedupe'] == 'created'
    r2 = prospects_repo.insert_prospect(lid, nom='Resto B', email='b@resto.fr',
                                        site_web='http://MONRESTO.FR/')
    assert r2['statut_dedupe'] == 'doublon'
    assert r2['prospect_id'] == r1['prospect_id']

    # Même téléphone normalisé (+33 / 0) → doublon
    r3 = prospects_repo.insert_prospect(lid, nom='Resto C', email='c@resto.fr',
                                        telephone='+33 6 12 34 56 78')
    assert r3['statut_dedupe'] == 'created'
    r4 = prospects_repo.insert_prospect(lid, nom='Resto C', email=None,
                                        telephone='0612345678')
    assert r4['statut_dedupe'] == 'doublon'


def test_import_cross_campagne_enrichit_pas_de_doublon(tmp_db):
    from database import prospects_repo
    from core.objectif_registry import resolve_or_create_campagne, import_lead_as_prospect
    c1, _ = resolve_or_create_campagne('Scraping Maps')
    c2, _ = resolve_or_create_campagne('Scraping Sniper')

    lead = {'nom': 'Boulangerie Dupont', 'site_web': 'https://dupont.bj',
            'email': 'contact@dupont.bj', 'telephone': '+22997000000', 'nb_avis': 120}

    r1 = import_lead_as_prospect(c1, lead, source='scraping')
    assert r1['statut_dedupe'] == 'created'

    # Objectif différent (autre campagne) : même site + email → enrichissement, pas de création
    lead2 = dict(lead, telephone='')
    r2 = import_lead_as_prospect(c2, lead2, source='scraping')
    assert r2['success']
    assert r2['statut_dedupe'] == 'updated'
    assert r2['prospect_id'] == r1['prospect_id']
    assert prospects_repo.list_prospects(campagne_id=c2)['leads'] == []


def test_import_lead_rejete_suppression_liste(tmp_db):
    from database import prospects_repo
    from core.objectif_registry import resolve_or_create_campagne, import_lead_as_prospect
    cid, _ = resolve_or_create_campagne('Cible')
    r = import_lead_as_prospect(cid, {'nom': 'Opt-out SARL', 'email': 'no@optout.fr'})
    assert r['success']
    pid = r['prospect_id']
    prospects_repo.set_ne_plus_contacter(pid, True)
    r2 = import_lead_as_prospect(cid, {'nom': 'Opt-out (rescrape)', 'email': 'no@optout.fr'})
    assert r2['statut_dedupe'] == 'suppression_list'


def test_import_lead_sans_nom_ni_email(tmp_db):
    from core.objectif_registry import resolve_or_create_campagne, import_lead_as_prospect
    cid, _ = resolve_or_create_campagne('Vide')
    r = import_lead_as_prospect(cid, {'nom': '', 'email': ''})
    assert not r['success']


# ─── Séquence & relances (routes) ─────────────────────────────────────────────

def test_transitions_endpoint(client):
    d = client.get('/api/v2/statuts/transitions').get_json()
    assert d['success']
    assert 'a_traiter_humain' in d['transitions']
    assert 'rdv_obtenu' in d['transitions']['a_traiter_humain']
    assert 'pas_interesse' in d['transitions']['a_traiter_humain']
    assert 'a_relancer_plus_tard' in d['transitions']['a_traiter_humain']
    assert d['transitions']['rdv_obtenu'] == []
    assert d['labels']['a_traiter_humain'] == 'À traiter'


def test_lead_detail_events(client):
    o = client.post('/api/v2/campagnes', json={'nom': 'Campagne detail'}).get_json()['campagne']
    res = client.post(f'/api/v2/campagnes/{o["id"]}/leads', json={'nom': 'Cible', 'email': 'cible@exemple.fr'}).get_json()
    pid = res['prospect_id']
    d = client.get(f'/api/v2/leads/{pid}').get_json()['lead']
    assert d['email'] == 'cible@exemple.fr'
    assert d['campagne_nom'] == 'Campagne detail'
    assert any(e['event_type'] == 'creation' for e in d['events'])
    assert client.get('/api/v2/leads/999999').get_json()['success'] is False


def test_sequence_routes_crud(client):
    from database import campagnes_repo
    cid = campagnes_repo.create_campagne('Séquence web')['campagne']['id']

    r = client.get(f'/api/v2/campagnes/{cid}/sequence')
    assert r.status_code == 200
    data = r.get_json()
    assert data['success']
    assert data['templates'] == [] or all(t['campagne_id'] != cid for t in data['templates'])

    r = client.post(f'/api/v2/campagnes/{cid}/sequence', json={
        'position': 1, 'delai_jours': 3, 'objet': 'Re: {{prenom}}', 'corps': 'Bonjour {{prenom}}',
    })
    assert r.status_code == 201
    tid = r.get_json()['id']
    assert tid

    r = client.get(f'/api/v2/campagnes/{cid}/sequence')
    tpl = [t for t in r.get_json()['templates'] if t['id'] == tid]
    assert tpl and tpl[0]['delai_jours'] == 3 and tpl[0]['position'] == 1

    r = client.put(f'/api/v2/sequence-templates/{tid}', json={'delai_jours': 7, 'actif': False})
    assert r.status_code == 200 and r.get_json()['success']
    r = client.get(f'/api/v2/campagnes/{cid}/sequence')
    tpl = [t for t in r.get_json()['templates'] if t['id'] == tid]
    assert tpl[0]['delai_jours'] == 7 and tpl[0]['actif'] == 0

    r = client.put('/api/v2/sequence-templates/999999', json={'delai_jours': 1})
    assert r.status_code == 404

    r = client.delete(f'/api/v2/sequence-templates/{tid}')
    assert r.status_code == 200
    r = client.get(f'/api/v2/campagnes/{cid}/sequence')
    assert all(t['id'] != tid for t in r.get_json()['templates'])

    r = client.get('/api/v2/campagnes/999999/sequence')
    assert r.status_code == 404