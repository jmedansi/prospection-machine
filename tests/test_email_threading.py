# -*- coding: utf-8 -*-
"""
tests/test_email_threading.py — threading RFC 2822 (v2).

Le fil de conversation vit dans `prospect_events` (cols message_id, in_reply_to,
references_header, parent_event_id, thread_id, direction) :
  - envoi sortant (initial/relance) : direction='out', branche du sequence_engine
  - réponse entrante (reply_poller) : direction='in', reliée à son parent sortant

Aucun réseau : gateway et hub Telegram monkeypatchés ; Resend testé via requests.post fake.
"""
from datetime import datetime

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
    schema.migrate_emails_threading()
    yield db_path


def _objectif(nom='Refonte site web', validation_telegram=0):
    from core.objectif_registry import resolve_or_create_campagne
    oid, _ = resolve_or_create_campagne(nom)
    from database.connection import get_conn
    with get_conn() as c:
        c.execute("UPDATE campagnes SET validation_telegram=?, max_touches=? WHERE id=?",
                  (validation_telegram, 3, oid))
        c.commit()
    return oid


def _prospect(oid, email='contact@dupont.fr'):
    from core.objectif_registry import get_or_create_liste
    from database import prospects_repo
    lid = get_or_create_liste(oid)
    return prospects_repo.insert_prospect(lid, nom='Boulangerie Dupont', email=email,
                                          prenom='M. Dupont', entreprise='Boulangerie Dupont',
                                          secteur='Boulangerie',
                                          data_extra={
                                              # Source de vérité du tunnel v2 : emails RÉDIGÉS.
                                              'email_objet':  'Première prise de contact {{prenom}}',
                                              'email_corps':  'Bonjour {{prenom}},\n\nVoici ma proposition.',
                                              'email_objet_2': 'Relance {{prenom}}',
                                              'email_corps_2': 'Bonjour {{prenom}},\n\nRelance n°1.',
                                          })['prospect_id']


def _seed_template_step(oid, position, objet=None, corps='Bonjour {{prenom}}, voici notre offre'):
    from envoi import template_registry
    return template_registry.add_or_update(campagne_id=oid, position=position,
                                           objet=objet or f'Objet pos {position}', corps=corps,
                                           delai_jours=0)


@pytest.fixture
def fake_gateway(monkeypatch):
    calls = []

    def _envoyer(message, boite=None):
        calls.append(dict(message))
        return {'success': True, 'statut': 'envoye',
                'message_id': f'mid-{len(calls)}',
                'boite': {'id': 9, 'email': 'boite@test.fr', 'backend': 'smtp'}}

    monkeypatch.setattr('envoi.sequence_engine.gateway.envoyer', _envoyer)
    return calls


# ─── Migration ──────────────────────────────────────────────────────────────

def test_migration_fraiche_prospect_events(tmp_db):
    from database.connection import get_conn
    with get_conn() as c:
        cols = {r[1] for r in c.execute("PRAGMA table_info(prospect_events)").fetchall()}
        assert {'message_id', 'in_reply_to', 'references_header',
                'parent_event_id', 'thread_id', 'direction'} <= cols
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
        assert 'idx_prospect_events_thread' in tables


def test_migration_alter_table_existante(tmp_path, monkeypatch):
    db_path = str(tmp_path / "legacy.db")
    monkeypatch.setattr(conn_mod, 'DB_PATH', db_path)
    monkeypatch.setattr('database.schema.connection.DB_PATH', db_path)
    from database.connection import get_conn
    with get_conn() as c:
        c.execute("""
            CREATE TABLE prospect_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prospect_id INTEGER NOT NULL,
                campagne_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT,
                mailbox_id INTEGER,
                message_id TEXT,
                in_reply_to TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        c.commit()
    from database import schema
    schema.migrate_emails_threading()
    with get_conn() as c:
        cols = {r[1] for r in c.execute("PRAGMA table_info(prospect_events)").fetchall()}
        assert {'references_header', 'parent_event_id', 'thread_id', 'direction'} <= cols


# ─── Helpers purs (envoi/threading.py) ─────────────────────────────────────

def test_ensure_re():
    from envoi.threading import ensure_re
    assert ensure_re('Bonjour') == 'Re: Bonjour'
    assert ensure_re('') == ''
    assert ensure_re('Re: déjà relancé') == 'Re: déjà relancé'
    assert ensure_re('FW: transféré') == 'FW: transféré'
    assert ensure_re('  avec espaces  ') == 'Re: avec espaces'


def test_extend_references():
    from envoi.threading import extend_references
    assert extend_references(None, '<a@x>') == '<a@x>'
    assert extend_references('<a@x>', '<b@x>') == '<a@x> <b@x>'
    assert extend_references('<a@x> <b@x>', '<b@x>') == '<a@x> <b@x>'
    assert extend_references('', None) == ''


# ─── SMTP : headers RFC 2822 ───────────────────────────────────────────────

def test_smtp_build_message_threading():
    from envoi import smtp_sender
    msg, mid = smtp_sender._build_message(
        'Test', 'test@domaine.fr', ['client@x.fr'], 'Sujet', '<p>Hello</p>',
        message_id='<impose@domaine.fr>', in_reply_to='<parent@x.fr>',
        references='<a@x.fr> <parent@x.fr>',
    )
    assert msg['Message-ID'] == '<impose@domaine.fr>'
    assert msg['In-Reply-To'] == '<parent@x.fr>'
    assert str(msg['References']) == '<a@x.fr> <parent@x.fr>'
    assert mid == '<impose@domaine.fr>'


def test_smtp_generates_message_id_quand_absent():
    from envoi import smtp_sender
    msg, mid = smtp_sender._build_message('T', 't@d.fr', ['c@x.fr'], 'S', 'bonjour')
    assert mid and mid.startswith('<') and mid.endswith('>')
    assert msg['Message-ID'] == mid
    assert msg['In-Reply-To'] is None


# ─── Envoi initial / relance : construction du fil ─────────────────────────

def test_initial_et_relance_construisent_le_fil(tmp_db, fake_gateway):
    from envoi.sequence_engine import send_initial, send_relance
    from database.connection import get_conn

    oid = _objectif()
    _seed_template_step(oid, 0, objet='Première prise de contact {{prenom}}')
    _seed_template_step(oid, 1, objet='Relance {{prenom}}')
    pid = _prospect(oid)

    r1 = send_initial(oid, pid, approval='auto', humanize_on=False)
    assert r1['success']

    with get_conn() as c:
        init = c.execute(
            "SELECT * FROM prospect_events WHERE prospect_id=? AND event_type='initial'",
            (pid,)).fetchone()
        assert init['direction'] == 'out'
        assert init['message_id'] == 'mid-1'
        assert init['in_reply_to'] is None
        assert init['references_header'] is None
        assert init['parent_event_id'] is None
        assert init['thread_id'] == init['id']   # racine du fil

    r2 = send_relance(oid, pid, approval='auto', humanize_on=False)
    assert r2['success']

    sent = fake_gateway[1]
    assert sent['in_reply_to'] == 'mid-1'
    assert sent['references'] == 'mid-1'
    assert sent['subject'].startswith('Re: ')

    with get_conn() as c:
        rel = c.execute(
            "SELECT * FROM prospect_events WHERE prospect_id=? AND event_type='relance_1'",
            (pid,)).fetchone()
        assert rel['direction'] == 'out'
        assert rel['message_id'] == 'mid-2'
        assert rel['in_reply_to'] == 'mid-1'
        assert rel['references_header'] == 'mid-1'
        assert rel['parent_event_id'] == init['id']
        assert rel['thread_id'] == init['thread_id']


# ─── Réponse entrante : rattachement au fil ────────────────────────────────

def test_reponse_entrante_rejoint_le_fil(tmp_db, fake_gateway):
    from envoi.sequence_engine import send_initial
    from envoi.reply_poller import handle_reply, find_parent_event, parse_reply
    from database.connection import get_conn

    oid = _objectif()
    _seed_template_step(oid, 0)
    pid = _prospect(oid)
    assert send_initial(oid, pid, approval='auto', humanize_on=False)['success']

    with get_conn() as c:
        init = c.execute("SELECT * FROM prospect_events WHERE prospect_id=? AND event_type='initial'",
                         (pid,)).fetchone()

    parsed = {
        'from_addr': 'contact@dupont.fr',
        'from_name': 'M. Dupont',
        'subject': 'Re: Première prise de contact',
        'date_iso': datetime.now().isoformat(timespec='seconds'),
        'message_id': '<reply1@dupont.fr>',
        'in_reply_to': 'mid-1',
        'references': 'mid-1',
        'body': 'Bonjour, très intéressé !',
        'content_type': 'text/plain',
        'raw': b'',
    }
    parent = find_parent_event(parsed)
    assert parent and parent['id'] == init['id']

    res = handle_reply(parsed, {'id': pid, 'campagne_id': oid}, 'reponse',
                       mailbox_email='boite@test.fr')
    assert res['success']

    with get_conn() as c:
        rep = c.execute("SELECT * FROM prospect_events WHERE prospect_id=? AND event_type='reponse'",
                        (pid,)).fetchone()
        assert rep['direction'] == 'in'
        assert rep['message_id'] == '<reply1@dupont.fr>'
        assert rep['in_reply_to'] == 'mid-1'
        assert rep['references_header'] == 'mid-1'
        assert rep['parent_event_id'] == init['id']
        assert rep['thread_id'] == init['thread_id']


def test_get_thread_for_lead_ordre_chronologique(tmp_db, fake_gateway):
    from envoi.sequence_engine import send_initial, send_relance
    from envoi.reply_poller import handle_reply
    from database.prospects import get_thread_for_lead

    oid = _objectif()
    _seed_template_step(oid, 0)
    _seed_template_step(oid, 1)
    pid = _prospect(oid)
    assert send_initial(oid, pid, approval='auto', humanize_on=False)['success']
    assert send_relance(oid, pid, approval='auto', humanize_on=False)['success']
    handle_reply({
        'from_addr': 'contact@dupont.fr', 'from_name': 'Dupont',
        'subject': 'Re: objet', 'date_iso': datetime.now().isoformat(timespec='seconds'),
        'message_id': '<r@x>', 'in_reply_to': 'mid-2', 'references': 'mid-1 mid-2',
        'body': 'ok', 'content_type': 'text/plain', 'raw': b'',
    }, {'id': pid, 'campagne_id': oid}, 'reponse')

    thread = get_thread_for_lead(pid)
    assert len(thread) == 3
    assert [t['event_type'] for t in thread] == ['initial', 'relance_1', 'reponse']
    root = thread[0]
    assert all(t['thread_id'] == root['thread_id'] for t in thread)


# ─── Resend : headers transmis à l'API ─────────────────────────────────────

def test_resend_transmet_headers_threading(tmp_db, monkeypatch):
    from database.db_manager import get_conn as mgr_conn
    with mgr_conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS resend_accounts (
            id INTEGER PRIMARY KEY, api_key TEXT, sender_email TEXT,
            sender_name TEXT, actif INTEGER DEFAULT 1,
            daily_usage INTEGER DEFAULT 0, last_reset TEXT)""")
        c.commit()

    from envoi import resend_sender as rs

    captured = {}
    monkeypatch.setattr(rs, 'get_next_resend_account',
                        lambda: {'id': 1, 'api_key': 'k', 'sender_email': 'x@domaine.fr',
                                 'sender_name': 'Jean'})

    def fake_post(url, json=None, headers=None, timeout=None):
        captured['payload'] = json
        class R:
            raise_for_status = lambda self: None
            json = lambda self: {'id': 'resend-internal-1'}
            text = ''
        return R()

    monkeypatch.setattr(rs.requests, 'post', fake_post)

    res = rs.send_prospecting_email('client@x.fr', 'Client', 'Sujet', 'Corps',
                                    in_reply_to='<parent@x.fr>',
                                    references='<a@x.fr> <parent@x.fr>')
    assert res['success']
    headers = {h['name']: h['value'] for h in captured['payload']['headers']}
    assert headers['In-Reply-To'] == '<parent@x.fr>'
    assert headers['References'] == '<a@x.fr> <parent@x.fr>'
    assert headers['Message-ID'].startswith('<')
    assert res['message_id'] == headers['Message-ID']
    assert res['resend_id'] == 'resend-internal-1'