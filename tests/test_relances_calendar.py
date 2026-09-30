# -*- coding: utf-8 -*-
"""
Tests v2 — calendrier des relances.

Couvre les deux contrats de `GET /api/v2/relances/calendar` :
  1. la liste concernée par chaque lot est exposée (filtre `liste_id` + champ `listes`) ;
  2. chaque lot reporte son ancre de calcul (`delai_jours` + `last_touch_at`) pour que
     la date projetée soit traçable « J+N jours ouvrés depuis le <touche de départ> ».
"""
from datetime import datetime, timedelta

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


def _seed_prospect(cid, lid, idx, days_ago):
    """Prospect `en_sequence` dont l'initial date de `days_ago` jours."""
    from database import prospects_repo
    from database.connection import get_conn

    pid = prospects_repo.insert_prospect(
        lid, nom=f'Agence {idx}', email=f'contact{idx}@exemple.fr',
        entreprise=f'Agence {idx}', secteur='Agence')['prospect_id']
    ts = (datetime.utcnow() - timedelta(days=days_ago)).strftime('%Y-%m-%d %H:%M:%S')
    with get_conn() as c:
        c.execute("UPDATE prospects SET statut='en_sequence' WHERE id=?", (pid,))
        c.execute(
            "INSERT INTO prospect_events (prospect_id, campagne_id, event_type, payload, created_at) "
            "VALUES (?, ?, 'initial', '{}', ?)",
            (pid, cid, ts))
        c.commit()
    return pid


def _dues(client, **params):
    import urllib.parse
    qs = urllib.parse.urlencode(params)
    res = client.get('/api/v2/relances/calendar' + ('?' + qs if qs else ''))
    assert res.status_code == 200
    data = res.get_json()
    assert data['success']
    out = []
    for day, group in data['days'].items():
        for b in group['batches']:
            if b['status'] == 'due':
                out.append((day, b))
    return data, out


# ─── Filtre + exposition de la liste ──────────────────────────────────────────

def test_le_calendrier_expose_les_listes_et_filtre_par_liste(client, tmp_db):
    from core.objectif_registry import get_or_create_liste, resolve_or_create_campagne
    from envoi import template_registry

    cid, _ = resolve_or_create_campagne('Agences digitales')
    lid_a = get_or_create_liste(cid, 'Liste A')
    lid_b = get_or_create_liste(cid, 'Liste B')

    template_registry.add_or_update(
        campagne_id=cid, position=1, nom='Relance 1', delai_jours=3,
        objet='Re: suite', corps='Bonjour')

    _seed_prospect(cid, lid_a, 1, days_ago=10)
    _seed_prospect(cid, lid_b, 2, days_ago=1)

    data, dues = _dues(client, campagne_id=cid)
    assert {l['id'] for l in data['listes']} >= {lid_a, lid_b}
    assert any(l['id'] == lid_a for l in data['listes'])

    # Filtre liste : seuls les lots de la liste demandée reviennent
    data_a, dues_a = _dues(client, campagne_id=cid, liste_id=lid_a)
    assert {l['id'] for l in data_a['listes']} == {lid_a}
    for day, batches in ((d, g['batches']) for d, g in data_a['days'].items()):
        for b in batches:
            assert b['liste_id'] == lid_a

    # Seule la liste A est due (initial il y a 10 j > 3 j ouvrés)
    assert dues_a, 'la liste A doit avoir au moins un lot dû'
    assert all(b['liste_id'] == lid_a for _d, b in dues_a)


# ─── Ancre du calcul ─────────────────────────────────────────────────────────

def test_les_lots_portent_delai_et_touche_de_depart(client, tmp_db):
    from core.objectif_registry import get_or_create_liste, resolve_or_create_campagne
    from core.orchestration import add_business_days
    from envoi import template_registry

    cid, _ = resolve_or_create_campagne('Agences SEO')
    lid = get_or_create_liste(cid, 'Liste SEO')
    template_registry.add_or_update(
        campagne_id=cid, position=1, nom='Relance 1', delai_jours=3,
        objet='Re: suite', corps='Bonjour')

    pid = _seed_prospect(cid, lid, 7, days_ago=10)
    from database.connection import get_conn
    with get_conn() as c:
        last = c.execute(
            "SELECT created_at FROM prospect_events WHERE prospect_id=? AND event_type='initial'",
            (pid,)).fetchone()['created_at']

    data, dues = _dues(client, campagne_id=cid, liste_id=lid)
    assert dues, 'un lot dû est attendu'

    day, batch = dues[0]
    assert batch['delai_jours'] == 3
    assert batch['last_touch_at'] == last

    last_dt = datetime.strptime(str(last)[:19], '%Y-%m-%d %H:%M:%S')
    assert day == add_business_days(last_dt, 3).strftime('%Y-%m-%d')


def test_les_lots_envoyes_gardent_une_ancre_renseignee(client, tmp_db):
    from core.objectif_registry import get_or_create_liste, resolve_or_create_campagne

    cid, _ = resolve_or_create_campagne('Agences Webdesign')
    lid = get_or_create_liste(cid, 'Liste WD')
    pid = _seed_prospect(cid, lid, 3, days_ago=10)

    ts = (datetime.utcnow() - timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S')
    from database.connection import get_conn
    with get_conn() as c:
        c.execute("UPDATE prospects SET statut='relance_1' WHERE id=?", (pid,))
        c.execute(
            "INSERT INTO prospect_events (prospect_id, campagne_id, event_type, payload, created_at) "
            "VALUES (?, ?, 'relance_1', '{}', ?)",
            (pid, cid, ts))
        c.commit()

    res = client.get('/api/v2/relances/calendar?campagne_id=%d' % cid)
    data = res.get_json()
    sent = [b for g in data['days'].values() for b in g['batches'] if b['status'] == 'sent']
    assert sent, 'un lot envoyé est attendu'
    for b in sent:
        assert b['liste_id'] == lid
        assert 'delai_jours' in b and 'last_touch_at' in b


# ── Corbeille : vue de tri, jamais une liste d'envoi ──────────────────────────

def test_la_corbeille_n_apparait_ni_au_calendrier_ni_aux_relances(client, tmp_db):
    from core.objectif_registry import get_or_create_liste, resolve_or_create_campagne
    from core.orchestration import relances_due
    from database.listes import get_or_create_corbeille, unlink_prospects
    from envoi import template_registry

    cid, _ = resolve_or_create_campagne('Agences IA')
    lid = get_or_create_liste(cid, 'Liste IA')
    template_registry.add_or_update(
        campagne_id=cid, position=1, nom='Relance 1', delai_jours=3,
        objet='Re: suite', corps='Bonjour')

    pid_actif = _seed_prospect(cid, lid, 11, days_ago=10)
    pid_sortant = _seed_prospect(cid, lid, 12, days_ago=10)

    # pid_sortant a déjà reçu une relance puis a été écarté → Corbeille
    ts = (datetime.utcnow() - timedelta(days=5)).strftime('%Y-%m-%d %H:%M:%S')
    from database.connection import get_conn
    with get_conn() as c:
        c.execute("UPDATE prospects SET statut='relance_1' WHERE id=?", (pid_sortant,))
        c.execute(
            "INSERT INTO prospect_events (prospect_id, campagne_id, event_type, payload, created_at) "
            "VALUES (?, ?, 'relance_1', '{}', ?)",
            (pid_sortant, cid, ts))
        c.commit()

    assert unlink_prospects(lid, [pid_sortant])['moved'] == 1
    corb = get_or_create_corbeille(cid)

    # Le type « corbeille » est porté par la liste, pas seulement par son nom
    with get_conn() as c:
        assert c.execute("SELECT type FROM listes WHERE id=?", (corb,)).fetchone()['type'] == 'corbeille'
        assert c.execute("SELECT type FROM listes WHERE id=?", (lid,)).fetchone()['type'] == 'normal'

    # Même resté en_sequence, le prospect rangé dans la corbeille n'est plus éligible
    assert [d['id'] for d in relances_due(cid)] == [pid_actif]

    # Et le calendrier ne montre ni la liste corbeille ni aucun de ses lots
    data, dues = _dues(client, campagne_id=cid)
    assert corb not in {l['id'] for l in data['listes']}
    assert lid in {l['id'] for l in data['listes']}
    for group in data['days'].values():
        for b in group['batches']:
            assert b['liste_id'] != corb, 'un lot de corbeille ne doit jamais apparaître'
    assert {b['liste_id'] for _d, b in dues} == {lid}
