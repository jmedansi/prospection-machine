# -*- coding: utf-8 -*-
"""tests/test_v2_replies.py — réponses entrantes (IMAP) → a_traiter_humain.

Aucun réseau : le fichier manipule des octets d'emails et un fake IMAP
(monkeypatch de `envoi.reply_poller._open_imap`).
"""
import json
import pytest
from email.message import EmailMessage
from email.utils import formatdate

import database.connection as conn_mod
from database.schema import init_db, migrate_db
from core.state_machine import transition_prospect


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "prospection_test.db"
    monkeypatch.setattr(conn_mod, 'DB_PATH', db_path)
    monkeypatch.setattr('database.schema.connection.DB_PATH', db_path)
    init_db()
    migrate_db()
    yield db_path


@pytest.fixture(autouse=True)
def no_telegram(monkeypatch):
    """Aucune notification Telegram réelle pendant les tests (hermétique réseau)."""
    from envoi import telegram_validation as tv
    monkeypatch.setattr(tv, 'notify_answer', lambda *a, **k: False)


def _mailbox(tmp_db, **kwargs):
    from database.connection import get_conn
    data = {
        'label': 'Boîte test', 'domaine': 'test.fr', 'email': 'prospection@test.fr',
        'smtp_host': 'smtp.test.fr', 'imap_host': 'imap.test.fr',
        'imap_user': 'prospection@test.fr', 'imap_pass': 'secret',
    }
    data.update(kwargs)
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO mailboxes
               (label, domaine, email, imap_host, imap_user, imap_pass)
               VALUES (?,?,?,?,?,?)""",
            (data['label'], data['domaine'], data['email'], data['imap_host'],
             data['imap_user'], data['imap_pass']),
        )
        conn.commit()
        return conn.execute("SELECT * FROM mailboxes WHERE id = ?", (cur.lastrowid,)).fetchone()


def _objectif(nom='Réponses web'):
    from database import objectifs_repo
    return objectifs_repo.create_objectif(nom)['objectif']['id']


def _prospect(oid, email='contact@dupont.fr'):
    from database import prospects_repo
    r = prospects_repo.insert_prospect(
        oid, nom='Boulangerie Dupont', email=email, ville='Cotonou',
        secteur='boulangerie', source='scraping')
    return r['prospect_id']


def _sent(pid):
    transition_prospect(pid, 'en_sequence', reason='initial envoyé')


def _raw_email(headers: dict):
    msg = EmailMessage()
    for k, v in headers.items():
        msg[k] = v
    msg.set_content(headers.get('body', 'Bonjour Jean-Marc, oui on peut se voir cette semaine.'))
    return msg.as_bytes()


def _parse(headers: dict):
    from envoi.reply_poller import parse_reply
    return parse_reply(_raw_email(headers))


# ─── parse / classify ─────────────────────────────────────────────────────────

def test_parse_reply_champs():
    p = _parse({
        'From': 'Boulangerie Dupont <contact@dupont.fr>',
        'To': 'prospection@test.fr',
        'Subject': 'Re: Votre site',
        'Date': formatdate(localtime=True),
        'Message-ID': '<reply1@dupont.fr>',
        'In-Reply-To': '<sent1@test.fr>',
        'body': 'Oui, je suis intéressé',
    })
    assert p['from_addr'] == 'contact@dupont.fr'
    assert p['from_name'] == 'Boulangerie Dupont'
    assert p['subject'] == 'Re: Votre site'
    assert p['message_id'] == '<reply1@dupont.fr>'
    assert p['in_reply_to'] == '<sent1@test.fr>'
    assert 'intéressé' in p['body']
    assert p['date_iso']


def test_classify_ndr_auto_reponse():
    from envoi.reply_poller import classify
    # NDR : expéditeur mailer-daemon
    assert classify(_parse({'From': 'MAILER-DAEMON@imap.test.fr',
                            'Subject': 'Undeliverable: Votre site'})) == 'ndr'
    # NDR : sujet delivery failed
    assert classify(_parse({'From': 'someone@x.fr',
                            'Subject': 'Delivery Status Notification (Failure)'})) == 'ndr'
    # Auto-reply : sujet OOO
    assert classify(_parse({'From': 'contact@dupont.fr',
                            'Subject': 'Out of Office: Re: Votre site'})) == 'auto_reply'
    # Auto-reply : expéditeur noreply
    assert classify(_parse({'From': 'noreply@google.com', 'Subject': 'Votre compte'})) == 'auto_reply'
    # Réponse réelle
    assert classify(_parse({'From': 'contact@dupont.fr',
                            'Subject': 'Re: Votre site'})) == 'reponse'


# ─── match / handle ───────────────────────────────────────────────────────────

def test_match_par_from_addr(tmp_db):
    from envoi.reply_poller import match_prospect
    oid = _objectif()
    pid = _prospect(oid)
    _sent(pid)
    p = match_prospect(_parse({'From': 'Boulangerie Dupont <CONTACT@dupont.fr>',
                               'Subject': 'Re: Votre site'}))
    assert p and p['id'] == pid
    # un prospect non séquencé (qualifie) n'est pas matché
    pid2 = _prospect(oid, email='autre@x.fr')
    assert match_prospect(_parse({'From': 'autre@x.fr', 'Subject': 'Hello'})) is None
    assert pid2


def test_match_par_message_id(tmp_db):
    from database.connection import get_conn
    from envoi.reply_poller import match_prospect
    oid = _objectif()
    pid = _prospect(oid)
    _sent(pid)
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO prospect_events (prospect_id, objectif_id, event_type, payload, message_id)
               VALUES (?,?, 'initial', '{}', ?)""",
            (pid, oid, '<sent1@test.fr>'),
        )
        conn.commit()
    p = match_prospect(_parse({'From': 'contact@dupont.fr',
                               'Subject': 'Re: Votre site',
                               'In-Reply-To': '<sent1@test.fr>'}))
    assert p and p['id'] == pid


def test_handle_reponse_transition_et_stats(tmp_db):
    from envoi.reply_poller import handle_reply
    from database import prospects_repo
    from database.stats import _stats_v2
    from database.connection import get_conn
    oid = _objectif()
    pid = _prospect(oid)
    _sent(pid)
    p = prospects_repo.get_prospect(pid)
    res = handle_reply(_parse({'From': 'contact@dupont.fr', 'Subject': 'Re: Votre site'}),
                       p, 'reponse', mailbox_email='prospection@test.fr')
    assert res['success'] and res['transition'] is True
    assert prospects_repo.get_prospect(pid)['statut'] == 'a_traiter_humain'
    with get_conn() as conn:
        ev = conn.execute(
            "SELECT * FROM prospect_events WHERE prospect_id=? AND event_type='reponse'",
            (pid,)).fetchone()
        assert ev and ev['payload']
        payload = json.loads(ev['payload'])
        assert payload['kind'] == 'reponse'
        assert payload['from_addr'] == 'contact@dupont.fr'
        assert payload['mailbox_email'] == 'prospection@test.fr'
    stats = _stats_v2(get_conn(), oid)
    assert stats['emails_repondus'] == 1
    assert stats['taux_reponse'] == 100
    assert stats['rdv_obtenus'] == 0


def test_handle_reponse_notifie_telegram(tmp_db, monkeypatch):
    """Une réponse réelle déclenche notify_answer (piloté calcul) — pas de NDR."""
    from envoi.reply_poller import handle_reply
    from envoi import telegram_validation as tv
    from database import prospects_repo
    calls = {}
    monkeypatch.setattr(tv, 'notify_answer',
                        lambda prospect, subject='', snippet='': calls.update(
                            subject=subject, snippet=snippet))
    oid = _objectif()
    pid = _prospect(oid)
    _sent(pid)
    handle_reply(_parse({'From': 'contact@dupont.fr', 'Subject': 'Re: Votre site'}),
                 prospects_repo.get_prospect(pid), 'reponse')
    assert calls.get('subject') == 'Re: Votre site'
    assert 'Bonjour Jean-Marc' in calls.get('snippet', '')


def test_handle_ndr_pas_de_transition(tmp_db):
    from envoi.reply_poller import handle_reply
    from database import prospects_repo
    oid = _objectif()
    pid = _prospect(oid)
    _sent(pid)
    res = handle_reply(_parse({'From': 'MAILER-DAEMON@test.fr',
                               'Subject': 'Undeliverable'}), prospects_repo.get_prospect(pid),
                       'ndr', mailbox_email='prospection@test.fr')
    assert res['transition'] is False
    assert prospects_repo.get_prospect(pid)['statut'] == 'en_sequence'
    # relance encore possible : il faut une touche initial (pour last_touch_at)
    from database.connection import get_conn
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO prospect_events (prospect_id, objectif_id, event_type, payload) VALUES (?,?, 'initial', '{}')",
            (pid, oid),
        )
        conn.commit()
    from core.orchestration import relances_due
    from envoi import template_registry
    template_registry.add_or_update(objectif_id=oid, position=1, delai_jours=0,
                                    objet='Re', corps='Re')
    assert relances_due(oid) and relances_due(oid)[0]['id'] == pid


def test_handle_reponse_réponse_déjà_reçue_pas_de_transition(tmp_db):
    from envoi.reply_poller import handle_reply
    from database import prospects_repo
    oid = _objectif()
    pid = _prospect(oid)
    _sent(pid)
    p = prospects_repo.get_prospect(pid)
    handle_reply(_parse({'From': 'contact@dupont.fr', 'Subject': 'Re: 1'}), p, 'reponse')
    handle_reply(_parse({'From': 'contact@dupont.fr', 'Subject': 'Re: 2',
                         'Message-ID': '<m2@x>'}), prospects_repo.get_prospect(pid), 'reponse')
    # toujours a_traiter_humain, pas d'exception, un seul status_change vers la cible
    assert prospects_repo.get_prospect(pid)['statut'] == 'a_traiter_humain'
    from database.connection import get_conn
    with get_conn() as conn:
        n = conn.execute("SELECT COUNT(*) c FROM prospect_events WHERE event_type='reponse' AND prospect_id=?",
                         (pid,)).fetchone()['c']
        assert n == 2
        sc = conn.execute(
            "SELECT COUNT(*) c FROM prospect_events WHERE event_type='status_change' AND prospect_id=?",
            (pid,)).fetchone()['c']
        assert sc == 2  # initial (qualifie→en_sequence) + 1 seule réponse


# ─── Poll avec fake IMAP ───────────────────────────────────────────────────────

class FakeIMAP:
    def __init__(self, emails):
        self._emails = emails
        self.store_calls = []
        self.logged_out = False

    def login(self, user, password):
        return ('OK', [b'LOGIN ok'])

    def select(self, mailbox):
        return ('OK', [b'1'])

    def search(self, charset, *criteria):
        ids = ' '.join(str(i) for i in range(1, len(self._emails) + 1))
        return ('OK', [ids.encode()]) if ids else ('OK', [b''])

    def fetch(self, msg_id, *args):
        idx = int(msg_id) - 1
        raw = self._emails[idx]
        return ('OK', [(b'%d (RFC822 {0}' % int(msg_id), raw)])

    def store(self, msg_id, typ, flags):
        self.store_calls.append((msg_id, typ, flags))
        return ('OK', [])

    def logout(self):
        self.logged_out = True
        return ('OK', [])


def test_poll_mailbox_traite_reponse_et_marque_seen(tmp_db, monkeypatch):
    import envoi.reply_poller as rp
    oid = _objectif()
    pid = _prospect(oid)
    _sent(pid)
    box = dict(_mailbox(tmp_db))
    reply = _raw_email({
        'From': 'Boulangerie Dupont <contact@dupont.fr>',
        'To': 'prospection@test.fr',
        'Subject': 'Re: Votre site',
        'Message-ID': '<r1@dupont.fr>',
        'body': 'Oui intéressé mais dites-moi en plus.',
    })
    fake = FakeIMAP([reply])
    monkeypatch.setattr(rp, '_open_imap', lambda m: fake)
    res = rp.poll_mailbox(box)
    assert res['success'] and res['scanned'] == 1 and res['reponse'] == 1
    assert res['transitions'] == 1
    assert len(fake.store_calls) == 1
    from database import prospects_repo
    assert prospects_repo.get_prospect(pid)['statut'] == 'a_traiter_humain'


def test_poll_mailbox_ignore_ndr_et_no_match(tmp_db, monkeypatch):
    import envoi.reply_poller as rp
    oid = _objectif()
    _prospect(oid)
    box = dict(_mailbox(tmp_db))
    fake = FakeIMAP([
        _raw_email({'From': 'MAILER-DAEMON@test.fr', 'Subject': 'Undeliverable',
                    'Message-ID': '<n1@x>'}),
        _raw_email({'From': 'inconnu@nullepart.fr', 'Subject': 'Hello',
                    'Message-ID': '<n2@x>'}),
    ])
    monkeypatch.setattr(rp, '_open_imap', lambda m: fake)
    res = rp.poll_mailbox(box)
    assert res['scanned'] == 2 and res['ndr'] == 1 and res['no_match'] == 1
    assert res['reponse'] == 0 and len(fake.store_calls) == 2
    del oid


def test_run_poll_boite_sans_creds_skip(tmp_db):
    from envoi.reply_poller import run_poll
    _mailbox(tmp_db, imap_host=None, imap_user=None, imap_pass=None)
    # pas de monkeypatch : _open_imap renvoie None sans réseau (creds absents)
    res = run_poll()
    assert res['success']
    assert res['summary'][0]['skipped'] == 'pas de creds IMAP'
    assert res['total_scanned'] == 0


# ─── Route API ────────────────────────────────────────────────────────────────

def test_recent_route(tmp_db):
    from flask import Flask
    from dashboard.routes.replies import replies_bp
    app = Flask(__name__)
    app.testing = True
    app.register_blueprint(replies_bp)
    client = app.test_client()

    assert client.get('/api/v2/replies/recent').get_json()['events'] == []

    oid = _objectif()
    pid = _prospect(oid)
    _sent(pid)
    from envoi.reply_poller import handle_reply
    from database import prospects_repo
    handle_reply(_parse({'From': 'contact@dupont.fr', 'Subject': 'Re: Votre site'}),
                 prospects_repo.get_prospect(pid), 'reponse')

    r = client.get('/api/v2/replies/recent')
    events = r.get_json()['events']
    assert len(events) == 1
    assert events[0]['event_type'] == 'reponse'
    assert events[0]['prospect_email'] == 'contact@dupont.fr'
    assert events[0]['payload']['subject'] == 'Re: Votre site'

    # poll anti-sans-réseau : boîte sans creds → skip, pas d'erreur
    _mailbox(tmp_db, imap_host=None, imap_user=None, imap_pass=None)
    r = client.post('/api/v2/replies/poll', json={'lookback_hours': 48})
    d = r.get_json()
    assert d['success'] and d['total_scanned'] == 0