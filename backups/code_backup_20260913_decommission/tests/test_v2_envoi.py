# -*- coding: utf-8 -*-
"""
Tests v2 — façade d'envoi unique envoi/gateway.py (envoyer(message, boîte)).

Chaque test utilise une base SQLite temporaire (fixture tmp_db).
Aucun email réel n'est envoyé (dry_run / absence de creds en test).
"""
import pytest

import database.connection as conn_mod
from database.schema import init_db, migrate_db


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "prospection_send_test.db"
    monkeypatch.setattr(conn_mod, 'DB_PATH', db_path)
    monkeypatch.setattr('database.schema.connection.DB_PATH', db_path)
    init_db()
    migrate_db()
    yield db_path


def _add_mailbox(email='commercial@zoho.fr', backend='smtp', quota=40, usage=0,
                 pool='*', port=587, host='smtp.zoho.eu', user='commercial@zoho.fr'):
    from database.connection import get_conn
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO mailboxes
               (label, domaine, email, smtp_host, smtp_port, smtp_user, smtp_pass,
                backend, quota_jour, usage_jour, objectif_pool)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            ('Zoho 1', 'zoho.fr', email, host, port, user, 'secret',
             backend, quota, usage, pool),
        )
        conn.commit()
        return cur.lastrowid


# ─── Sélection de boîte ────────────────────────────────────────────────────────

def test_get_next_mailbox_rotation_et_quota(tmp_db):
    from envoi.gateway import get_next_mailbox
    _add_mailbox(email='a@zoho.fr', usage=5, quota=40)
    _add_mailbox(email='b@zoho.fr', usage=0, quota=40)
    _add_mailbox(email='epuise@zoho.fr', usage=40, quota=40)  # quota atteint
    box = get_next_mailbox()
    assert box is not None
    assert box['email'] == 'b@zoho.fr'  # usage le plus bas

    # quota 0 → boîte épuisée exclue
    _add_mailbox(email='zero@zoho.fr', usage=0, quota=0)
    assert all('zero' not in (get_next_mailbox() or {}).get('email', '') for _ in range(3))
    assert get_next_mailbox()['usage_jour'] == 0


def test_get_next_mailbox_backend_pref(tmp_db):
    from envoi.gateway import get_next_mailbox
    _add_mailbox(email='smtp@zoho.fr', backend='smtp')
    _add_mailbox(email='res@resend.io', backend='resend')
    assert get_next_mailbox(backend_pref='smtp')['backend'] == 'smtp'
    assert get_next_mailbox(backend_pref='resend')['backend'] == 'resend'
    assert get_next_mailbox(backend_pref='auto')['backend'] in ('smtp', 'resend')


def test_get_next_mailbox_pool_objectif(tmp_db):
    import json
    from envoi.gateway import get_next_mailbox
    _add_mailbox(email='general@zoho.fr', pool='*')
    _add_mailbox(email='pool3@zoho.fr', pool=json.dumps([1, 2]))
    box = get_next_mailbox(objectif_id=3)
    assert box['email'] == 'general@zoho.fr'  # réservée objectifs 1-2 exclue
    box = get_next_mailbox(objectif_id=2)
    assert box['email'] in ('pool3@zoho.fr', 'general@zoho.fr')


# ─── Envoi (dry_run) & compteurs ───────────────────────────────────────────────

def test_envoyer_dry_run_reussit_sans_incrementer(tmp_db):
    from envoi.gateway import envoyer
    mid = _add_mailbox(email='dry@zoho.fr', usage=7)
    r = envoyer({
        'to': 'client@exemple.fr', 'nom': 'SARL Client',
        'subject': 'Un mot sur votre site', 'corps': '<p>Bonjour</p>',
        'dry_run': True,
    })
    assert r['success']
    assert r['statut'] == 'dry_run'
    assert r['boite'] is not None and r['boite']['email'] == 'dry@zoho.fr'
    # dry_run ne consomme PAS le quota de la boîte
    from database.connection import get_conn
    with get_conn() as conn:
        usage = conn.execute("SELECT usage_jour FROM mailboxes WHERE id = ?", (mid,)).fetchone()[0]
    assert usage == 7


def test_envoyer_objet_inexistant_renvoie_erreur(tmp_db):
    from envoi.gateway import envoyer
    r = envoyer({'to': '', 'dry_run': True})
    assert not r['success']
    assert r['statut'] == 'erreur_config'


def test_envoyer_pas_de_boite_eligible_sans_dryrun(tmp_db):
    from envoi.gateway import envoyer
    _add_mailbox(email='full@zoho.fr', usage=80, quota=80)  # toutes épuisées
    r = envoyer({'to': 'q@example.fr', 'subject': 's', 'corps': 'c', 'dry_run': False})
    assert not r['success']
    assert 'éligible' in r['erreur']


# ─── Seed depuis .env ──────────────────────────────────────────────────────────

def test_seed_boite_depuis_env_si_table_vide(tmp_db, monkeypatch):
    from envoi.gateway import get_next_mailbox
    from core.config import ensure_env
    monkeypatch.setenv('SMTP_HOST', 'smtp.zoho.eu')
    monkeypatch.setenv('SMTP_USER', 'commercial@zoho.eu')
    monkeypatch.setenv('SMTP_PASSWORD', 'topsecret')
    monkeypatch.setenv('SMTP_PORT', '465')
    box = get_next_mailbox()
    assert box is not None
    assert box['smtp_host'] == 'smtp.zoho.eu'
    assert box['email'] == 'commercial@zoho.eu'
    # idempotent : pas de 2e boîte
    box2 = get_next_mailbox()
    assert box2['id'] == box['id']