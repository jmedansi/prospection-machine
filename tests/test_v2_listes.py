# -*- coding: utf-8 -*-
"""
Tests v2 — Listes (schéma v2, repo `database/listes.py`, API `/api/v2/listes`).

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


def _cid(client, nom='Campagne base'):
    client.post('/api/v2/campagnes', json={'nom': nom})
    return client.get('/api/v2/campagnes').get_json()['campagnes'][0]['id']


# ─── Repo listes ───────────────────────────────────────────────────────────────

def test_create_liste_nom_requis_et_campagne_requise(tmp_db):
    from database import listes_repo
    from database import campagnes_repo
    cid = campagnes_repo.create_campagne('C1')['campagne']['id']
    r = listes_repo.create_liste(cid, 'Lyon')
    assert r['success']
    assert r['liste']['nom'] == 'Lyon'
    assert r['liste']['campagne_id'] == cid
    assert not listes_repo.create_liste(cid, '   ')['success']
    assert not listes_repo.create_liste(None, 'Nom')['success']
    assert not listes_repo.create_liste(999999, 'Nom')['success']


def test_list_listes_filtres(tmp_db):
    from database import listes_repo
    from database import campagnes_repo
    c1 = campagnes_repo.create_campagne('Paris camp')['campagne']['id']
    c2 = campagnes_repo.create_campagne('Lyon camp')['campagne']['id']
    l1 = listes_repo.create_liste(c1, 'Arrondissements')['liste']['id']
    l2 = listes_repo.create_liste(c1, 'Banlieue', secteur='Logistique')['liste']['id']
    listes_repo.create_liste(c2, 'Rhône', secteur='Logistique')

    assert len(listes_repo.list_listes()) == 5  # auto Paris + 2 crées + auto Lyon + Rhône
    only_c1 = listes_repo.list_listes(campagne_id=c1)
    assert {l['nom'] for l in only_c1} == {'Arrondissements', 'Banlieue', 'Paris camp'}
    by_statut = listes_repo.list_listes(statut='actif')
    assert all(l['statut'] == 'actif' for l in by_statut)
    search = listes_repo.list_listes(search='Logistique')
    assert {l['nom'] for l in search} == {'Banlieue', 'Rhône'}


def test_archiver_et_supprimer_liste(tmp_db):
    from database import listes_repo, prospects_repo
    from database import campagnes_repo
    from core.objectif_registry import get_or_create_liste
    cid = campagnes_repo.create_campagne('C')['campagne']['id']
    lid = get_or_create_liste(cid)
    prospects_repo.insert_prospect(lid, nom='A', email='a@a.fr')

    assert not listes_repo.update_liste(999999, nom='X')['success']
    r = listes_repo.update_liste(lid, nom='Liste renommée', secteur='Sante')
    assert r['success']
    assert r['liste']['nom'] == 'Liste renommée'

    r = listes_repo.archive_liste(lid)
    assert r['success']
    active = listes_repo.list_listes(campagne_id=cid, include_archives=False)
    assert lid not in [l['id'] for l in active]
    archived = listes_repo.list_listes(campagne_id=cid, include_archives=True)
    assert lid in [l['id'] for l in archived]

    r = listes_repo.delete_liste(lid)
    assert r['success']
    # suppression en cascade → plus aucun prospect dans la liste
    assert listes_repo.list_listes(campagne_id=cid, include_archives=True) == []
    left = prospects_repo.list_prospects(campagne_id=cid)
    assert left['total'] == 0


def test_nb_leads_et_derniere_touche(tmp_db):
    from database import listes_repo, prospects_repo
    from database import campagnes_repo
    from core.objectif_registry import get_or_create_liste
    from core.state_machine import transition_prospect
    cid = campagnes_repo.create_campagne('C')['campagne']['id']
    lid = get_or_create_liste(cid)
    pid = prospects_repo.insert_prospect(lid, nom='X', email='x@x.fr')['prospect_id']
    transition_prospect(pid, 'en_sequence', reason='initial')
    row = listes_repo.list_listes(campagne_id=cid)[0]
    assert row['nb_leads'] == 1
    assert row['derniere_touche'] is not None
    assert row['campagne_nom'] == 'C'


# ─── API v2 : listes ───────────────────────────────────────────────────────────

def test_api_crud_liste(client):
    cid = _cid(client)
    r = client.post('/api/v2/listes', json={'campagne_id': cid, 'nom': 'Lyon'})
    assert r.status_code == 201
    lid = r.get_json()['liste']['id']

    lst = client.get('/api/v2/listes?campagne_id=%d' % cid).get_json()['listes']
    assert lst and lst[0]['campagne_nom'] == 'Campagne base'

    r = client.put(f'/api/v2/listes/{lid}', json={'nom': 'Lyon centre'})
    assert r.status_code == 200
    assert r.get_json()['liste']['nom'] == 'Lyon centre'

    assert client.post('/api/v2/listes', json={'nom': 'sans campagne'}).status_code == 400

    r = client.post(f'/api/v2/listes/{lid}/archive', json={'archiver': True})
    assert r.status_code == 200 and r.get_json()['success']

    r = client.delete(f'/api/v2/listes/{lid}')
    assert r.status_code == 200 and r.get_json()['success']
    rest = client.get('/api/v2/listes?campagne_id=%d' % cid).get_json()['listes']
    assert all(l['id'] != lid for l in rest)  # reste la liste auto 'Campagne base'


def test_api_import_et_leads_dans_liste(client):
    cid = _cid(client)
    creation = client.post('/api/v2/listes', json={'campagne_id': cid, 'nom': 'Grand Est'})
    lid = creation.get_json()['liste']['id']

    r = client.post(f'/api/v2/listes/{lid}/leads/import', json={'rows': [
        {'nom': 'Boucherie Martin', 'email': 'bm@martin.fr', 'ville': 'Metz'},
        {'nom': 'Dupont', 'email': 'dupont@exemple.fr'},
    ]})
    assert r.status_code == 200
    assert r.get_json()['importes'] == 2

    r = client.get(f'/api/v2/listes/{lid}/leads?limit=10')
    leads = r.get_json()['leads']
    assert len(leads) == 2
    assert leads[0]['liste_nom'] == 'Grand Est'
    assert leads[0]['campagne_nom'] == 'Campagne base'

    detail = client.get(f'/api/v2/listes').get_json()['listes']
    row = [l for l in detail if l['id'] == lid][0]
    assert row['nb_leads'] == 2


def test_import_dans_listes_distinctes_isole(tmp_db, client):
    cid = _cid(client, 'Multi listes')
    l1 = client.post('/api/v2/listes', json={'campagne_id': cid, 'nom': 'L1'}).get_json()['liste']['id']
    l2 = client.post('/api/v2/listes', json={'campagne_id': cid, 'nom': 'L2'}).get_json()['liste']['id']
    client.post(f'/api/v2/listes/{l1}/leads/import', json={'rows': [
        {'nom': 'Cible A', 'email': 'a@a.fr'},
        {'nom': 'Cible B', 'email': 'b@b.fr'},
    ]})
    client.post(f'/api/v2/listes/{l2}/leads/import', json={'rows': [
        {'nom': 'Cible C', 'email': 'c@c.fr'},
    ]})
    assert client.get(f'/api/v2/listes/{l1}/leads').get_json()['total'] == 2
    assert client.get(f'/api/v2/listes/{l2}/leads').get_json()['total'] == 1
    assert client.get(f'/api/v2/campagnes/{cid}/leads').get_json()['total'] == 3


def test_import_liste_inexistante_404(client):
    assert client.post('/api/v2/listes/424242/leads/import',
                       json={'rows': [{'nom': 'X'}]}).status_code == 404