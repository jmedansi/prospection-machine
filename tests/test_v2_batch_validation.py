# -*- coding: utf-8 -*-
"""
tests/test_v2_batch_validation.py — validation Telegram PAR LOT des relances v2.

Couvre `core.relance_batch_validator` :
- `ensure_batch_requests` : une seule demande par liste (callback v2_batch_{c}_{l}),
  idempotente (pending → pas de re-demande), absente pour une campagne sans
  `validation_relances`.
- `consume_approvals` : ✅ → run_relances(liste, approval='auto') + statut 'sent' ;
  ❌ → 'refuse', rien n'est envoyé.
Monkeypatch hub Telegram + orchestration (aucun réseau réel).
"""
import pytest

from database import connection as conn_mod


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test_batch.db")
    monkeypatch.setattr(conn_mod, 'DB_PATH', db_path)
    monkeypatch.setattr('database.schema.connection.DB_PATH', db_path)
    from database import schema
    schema.init_db()
    schema.migrate_v2_schema()
    yield db_path


def _campagne(nom='Refonte site web', validation_relances=1):
    from core.objectif_registry import resolve_or_create_campagne
    oid, _ = resolve_or_create_campagne(nom)
    from database.connection import get_conn
    with get_conn() as c:
        c.execute("UPDATE campagnes SET validation_relances=?, envoi_auto=1 WHERE id=?",
                  (validation_relances, oid))
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


def _to_en_sequence(pid, oid, days_ago=1):
    from datetime import datetime, timedelta
    from core.state_machine import transition_prospect
    transition_prospect(pid, 'en_sequence', reason='initial (test)')
    from database.connection import get_conn
    ts = (datetime.utcnow() - timedelta(days=days_ago)).strftime('%Y-%m-%d %H:%M:%S')
    with get_conn() as c:
        c.execute("INSERT INTO prospect_events (prospect_id, campagne_id, event_type, payload, created_at) VALUES (?,?,?,?,?)",
                  (pid, oid, 'initial', '{}', ts))
        c.commit()


@pytest.fixture
def fake_hub(monkeypatch):
    """Hub Telegram factice : send_validation_request → 'pending', get_status piloté."""
    store = {'status': {}, 'completed': []}
    import core.telegram_adapter as ta

    def _send(outil, preview, callback_id, timeout_minutes=None, titre=None):
        store['last'] = {'outil': outil, 'preview': preview, 'callback_id': callback_id,
                         'titre': titre, 'timeout_minutes': timeout_minutes}
        return 'pending'

    monkeypatch.setattr(ta, 'send_validation_request', _send)
    import envoi.telegram_validation as tv
    monkeypatch.setattr(tv, 'get_status', lambda cb: store['status'].get(cb))
    monkeypatch.setattr(tv, 'mark_completed',
                        lambda cb: (store['completed'].append(cb), True)[1])
    return store


@pytest.fixture(autouse=True)
def fenetre_ouverte(monkeypatch):
    """Par défaut la fenêtre horaire est ouverte (sinon les tests dépendent de l'heure
    à laquelle ils tournent). Les tests qui couvrent la fenêtre la referment."""
    monkeypatch.setattr('core.orchestration.is_fenetre_relances', lambda dt=None: True)


def test_aucune_demande_hors_fenetre_horaire(tmp_db, fake_hub, monkeypatch):
    """Pas de demande Telegram la nuit (elle réveillait l'utilisateur à 01h00)."""
    monkeypatch.setattr('core.orchestration.is_fenetre_relances', lambda dt=None: False)
    oid = _campagne(validation_relances=1)
    _seed_template_step(oid, 1, delai_jours=0)
    pid = _prospect(oid)
    _to_en_sequence(pid, oid)
    from core.relance_batch_validator import ensure_batch_requests
    from database.connection import get_conn
    res = ensure_batch_requests()
    assert res['requests'] == [] and res['differee'] is True
    assert fake_hub.get('last') is None
    with get_conn() as c:
        assert c.execute("SELECT COUNT(*) FROM relance_batches").fetchone()[0] == 0


def test_validation_nuit_conservee_pas_envoyee(tmp_db, fake_hub, spy_run_relances,
                                               monkeypatch):
    """✅ donnée la nuit : RIEN n'est consommé, la réponse part à l'ouverture."""
    oid = _campagne(validation_relances=1)
    _seed_template_step(oid, 1, delai_jours=0)
    pid = _prospect(oid)
    _to_en_sequence(pid, oid)
    from core.relance_batch_validator import (ensure_batch_requests, consume_approvals,
                                              batch_callback)
    from database.connection import get_conn
    with get_conn() as c:
        lid = c.execute("SELECT liste_id FROM prospects WHERE id=?", (pid,)).fetchone()[0]
    ensure_batch_requests()
    cb = batch_callback(oid, lid)
    fake_hub['status'][cb] = 'ok'
    monkeypatch.setattr('core.orchestration.is_fenetre_relances', lambda dt=None: False)
    res = consume_approvals()
    assert res['consumed'] == [] and res['differee'] is True
    assert spy_run_relances == []
    assert fake_hub['completed'] == []          # ✅ pas consommée
    with get_conn() as c:
        assert c.execute("SELECT statut FROM relance_batches WHERE callback_id=?",
                         (cb,)).fetchone()[0] == 'pending'
    # Ouverture de la fenêtre → le poll suivant envoie le lot
    monkeypatch.setattr('core.orchestration.is_fenetre_relances', lambda dt=None: True)
    res2 = consume_approvals()
    assert res2['consumed'][0]['statut'] == 'sent'
    assert spy_run_relances == [{'campagne_id': oid, 'liste_id': lid, 'approval': 'auto'}]


def test_echec_technique_retry_puis_erreur(tmp_db, fake_hub, monkeypatch):
    """Une erreur d'envoi ne doit JAMAIS clore le lot ni perdre la ✅."""
    oid = _campagne(validation_relances=1)
    _seed_template_step(oid, 1, delai_jours=0)
    pid = _prospect(oid)
    _to_en_sequence(pid, oid)
    from core.relance_batch_validator import (ensure_batch_requests, consume_approvals,
                                              batch_callback)
    import core.relance_batch_validator as rbv
    from database.connection import get_conn
    with get_conn() as c:
        lid = c.execute("SELECT liste_id FROM prospects WHERE id=?", (pid,)).fetchone()[0]
    ensure_batch_requests()
    cb = batch_callback(oid, lid)
    fake_hub['status'][cb] = 'ok'

    def _boom(*a, **kw):
        raise Exception("database is locked")

    monkeypatch.setattr('core.orchestration.run_relances', _boom)
    for tentative in range(1, rbv._MAX_TENTATIVES):
        res = consume_approvals()
        assert res['consumed'] == []
        with get_conn() as c:
            row = c.execute("SELECT statut, tentatives FROM relance_batches WHERE callback_id=?",
                            (cb,)).fetchone()
        assert row[0] == 'pending' and row[1] == tentative   # rejoué au poll suivant
        assert fake_hub['completed'] == []                  # ✅ jamais consommée
    # Échec définitif → 'erreur' + ✅ consommée (pas de boucle de retries)
    res = consume_approvals()
    assert res['consumed'] == []
    with get_conn() as c:
        row = c.execute("SELECT statut, tentatives FROM relance_batches WHERE callback_id=?",
                        (cb,)).fetchone()
    assert row[0] == 'erreur' and row[1] == rbv._MAX_TENTATIVES
    assert fake_hub['completed'] == [cb]
    # Un lot en erreur inchangé n'est pas re-demandé automatiquement
    assert ensure_batch_requests()['requests'] == []


def test_lot_sending_orphelin_repris(tmp_db, fake_hub, spy_run_relances):
    """Un lot 'sending' (process mort en plein envoi) redevient consommable."""
    oid = _campagne(validation_relances=1)
    _seed_template_step(oid, 1, delai_jours=0)
    pid = _prospect(oid)
    _to_en_sequence(pid, oid)
    from core.relance_batch_validator import (ensure_batch_requests, consume_approvals,
                                              batch_callback)
    from database.connection import get_conn
    with get_conn() as c:
        lid = c.execute("SELECT liste_id FROM prospects WHERE id=?", (pid,)).fetchone()[0]
    ensure_batch_requests()
    cb = batch_callback(oid, lid)
    with get_conn() as c:
        c.execute("UPDATE relance_batches SET statut='sending', "
                  "updated_at=datetime('now','-1 hour') WHERE callback_id=?", (cb,))
        c.commit()
    fake_hub['status'][cb] = 'ok'
    res = consume_approvals()
    assert res['consumed'][0]['statut'] == 'sent'


@pytest.fixture
def spy_run_relances(monkeypatch):
    calls = []

    def _run(campagne_id=None, limit_per_campagne=20, manual=False, *, objectif_id=None,
             liste_id=None, approval=None):
        calls.append({'campagne_id': campagne_id, 'liste_id': liste_id, 'approval': approval})
        return {'success': True, 'total': 2, 'runs': []}

    monkeypatch.setattr('core.orchestration.run_relances', _run)
    return calls


def test_notification_lisible_et_echappee(tmp_db, fake_hub):
    """La demande Telegram doit être TITRÉE (pas le callback brut `v2_batch_44_180`)
    et échappée : un nom de liste avec `_` casse le parseur Markdown et la demande
    n'est jamais envoyée."""
    oid = _campagne(nom='Agences digitales', validation_relances=1)
    _seed_template_step(oid, 1, delai_jours=0)
    pid = _prospect(oid)
    _to_en_sequence(pid, oid)
    from core.relance_batch_validator import ensure_batch_requests
    from database.connection import get_conn
    with get_conn() as c:
        lid = c.execute("SELECT liste_id FROM prospects WHERE id=?", (pid,)).fetchone()[0]
        c.execute("UPDATE listes SET nom=? WHERE id=?", ('Studio_Web_UX', lid))
        c.commit()
    ensure_batch_requests()
    last = fake_hub['last']
    # Titre lisible, callback brut absent du texte
    assert last['titre'] and 'Studio' in last['titre'] and 'UX' in last['titre']
    assert 'v2_batch_' not in last['titre']
    assert 'V2_BATCH' not in last['preview'].upper()
    # Markdown échappé : plus aucun `_` nu dans le corps
    assert 'Studio_Web_UX' not in last['preview']
    assert last['preview'].count('\\_') >= 2
    # Timeout réel transmis (48 h), pas le 10 min du config.json
    assert last['timeout_minutes'] == 2880
    # `outil` part en texte PLAIN (affiché par bot.py sans parse_mode) : jamais échappé
    assert last['outil'] == 'Relances — Studio_Web_UX'


def test_demande_ciblee_une_seule_liste(tmp_db, fake_hub):
    """Le bouton « Déclencher Telegram » ne doit demander QUE la liste cliquée :
    sans filtre, chaque clic notifiait TOUTES les listes dues."""
    oid = _campagne(validation_relances=1)
    _seed_template_step(oid, 1, delai_jours=0)
    p1 = _prospect(oid, email='a@test.fr')
    _to_en_sequence(p1, oid)
    from core.relance_batch_validator import ensure_batch_requests, batch_callback
    from database import listes as listes_db
    from database.connection import get_conn
    with get_conn() as c:
        lid1 = c.execute("SELECT liste_id FROM prospects WHERE id=?", (p1,)).fetchone()[0]
    lid2 = listes_db.create_liste(oid, 'Autre liste')['liste']['id']
    with get_conn() as c:
        pid2 = c.execute(
            "INSERT INTO prospects (liste_id, nom, email, statut, created_at) "
            "VALUES (?, ?, ?, 'qualifie', datetime('now'))",
            (lid2, 'Autre', 'b@test.fr')).lastrowid
    _to_en_sequence(pid2, oid)

    res = ensure_batch_requests(campagne_id=oid, liste_id=lid1)
    assert len(res['requests']) == 1
    assert res['requests'][0]['callback_id'] == batch_callback(oid, lid1)

    # Sans filtre (comportement du scheduler) → l'AUTRE liste est aussi demandée,
    # ce que le clic ciblé avait justement évité.
    res_all = ensure_batch_requests(campagne_id=oid)
    assert {r['liste_id'] for r in res_all['requests']} == {lid2}


def test_force_redemande_un_lot_refuse(tmp_db, fake_hub, spy_run_relances):
    """`force=True` (bouton UI) re-demande un lot `refuse` ; le job auto, lui, ne
    redemande rien tant que le lot est inchangé."""
    oid = _campagne(validation_relances=1)
    _seed_template_step(oid, 1, delai_jours=0)
    pid = _prospect(oid)
    _to_en_sequence(pid, oid)
    from core.relance_batch_validator import (ensure_batch_requests, consume_approvals,
                                              batch_callback)
    from database.connection import get_conn
    with get_conn() as c:
        lid = c.execute("SELECT liste_id FROM prospects WHERE id=?", (pid,)).fetchone()[0]
    ensure_batch_requests()
    cb = batch_callback(oid, lid)
    fake_hub['status'][cb] = 'no'
    consume_approvals()   # → 'refuse'
    with get_conn() as c:
        assert c.execute("SELECT statut FROM relance_batches WHERE callback_id=?",
                         (cb,)).fetchone()[0] == 'refuse'
    # Auto : pas de re-demande
    snapshot = dict(fake_hub['last'])
    assert ensure_batch_requests()['requests'] == []
    assert fake_hub['last'] == snapshot     # aucune nouvelle notification envoyée
    # Forcé (UI) : nouvelle notification, le callback repart en 'pending'
    fake_hub['status'][cb] = None
    res = ensure_batch_requests(campagne_id=oid, liste_id=lid, force=True)
    assert len(res['requests']) == 1 and res['requests'][0]['callback_id'] == cb
    with get_conn() as c:
        row = c.execute("SELECT statut, tentatives FROM relance_batches WHERE callback_id=?",
                        (cb,)).fetchone()
    assert row[0] == 'pending' and row[1] == 0


def test_format_timeout_hub():
    """Le timeout affiché doit être lisible (48 h), pas « 2880 min »."""
    import sys
    hub = r'D:\hub_telegram\_system_hub'
    if hub not in sys.path:
        sys.path.insert(0, hub)
    import importlib
    notifier = importlib.import_module('telegram_notifier')
    fmt = notifier._format_timeout
    assert fmt(10) == '10 min'
    assert fmt(2880) == '2 j'
    assert fmt(120) == '2 h'
    assert fmt(90) == '1.5 h'


def test_aucun_lot_sans_validation_relances(tmp_db, fake_hub):
    oid = _campagne(validation_relances=0)
    _seed_template_step(oid, 1, delai_jours=0)
    pid = _prospect(oid)
    _to_en_sequence(pid, oid)
    from core.relance_batch_validator import ensure_batch_requests
    res = ensure_batch_requests()
    assert res['requests'] == []


def test_un_lot_par_liste_et_idempotence(tmp_db, fake_hub):
    oid = _campagne(validation_relances=1)
    _seed_template_step(oid, 1, delai_jours=0)
    p1 = _prospect(oid, email='a@test.fr')
    p2 = _prospect(oid, email='b@test.fr')
    _to_en_sequence(p1, oid)
    _to_en_sequence(p2, oid)
    from core.relance_batch_validator import ensure_batch_requests, batch_callback
    from database.connection import get_conn
    lid = None
    with get_conn() as c:
        lid = c.execute("SELECT liste_id FROM prospects WHERE id=?", (p1,)).fetchone()[0]
    res = ensure_batch_requests()
    assert len(res['requests']) == 1
    req = res['requests'][0]
    assert req['callback_id'] == batch_callback(oid, lid)
    assert req['campagne_id'] == oid and req['liste_id'] == lid
    assert req['count'] == 2 and req['position'] == 1
    with get_conn() as c:
        row = c.execute("SELECT statut, count FROM relance_batches WHERE callback_id=?",
                        (req['callback_id'],)).fetchone()
        assert row and row[0] == 'pending' and row[1] == 2
    # Idempotence : second passage → aucune nouvelle demande
    store_before = dict(fake_hub.get('last'))
    res2 = ensure_batch_requests()
    assert len(res2['requests']) == 0
    assert fake_hub.get('last') == store_before


def test_consomme_ok_et_envoie_le_lot(tmp_db, fake_hub, spy_run_relances):
    oid = _campagne(validation_relances=1)
    _seed_template_step(oid, 1, delai_jours=0)
    pid = _prospect(oid)
    _to_en_sequence(pid, oid)
    from core.relance_batch_validator import (ensure_batch_requests, consume_approvals,
                                              batch_callback)
    from database.connection import get_conn
    with get_conn() as c:
        lid = c.execute("SELECT liste_id FROM prospects WHERE id=?", (pid,)).fetchone()[0]
    ensure_batch_requests()
    cb = batch_callback(oid, lid)
    fake_hub['status'][cb] = 'ok'
    res = consume_approvals()
    assert len(res['consumed']) == 1 and res['consumed'][0]['statut'] == 'sent'
    assert spy_run_relances == [{'campagne_id': oid, 'liste_id': lid, 'approval': 'auto'}]
    with get_conn() as c:
        assert c.execute("SELECT statut FROM relance_batches WHERE callback_id=?",
                         (cb,)).fetchone()[0] == 'sent'


def test_consomme_no_refuse_sans_envoi(tmp_db, fake_hub, spy_run_relances):
    oid = _campagne(validation_relances=1)
    _seed_template_step(oid, 1, delai_jours=0)
    pid = _prospect(oid)
    _to_en_sequence(pid, oid)
    from core.relance_batch_validator import (ensure_batch_requests, consume_approvals,
                                              batch_callback)
    from database.connection import get_conn
    with get_conn() as c:
        lid = c.execute("SELECT liste_id FROM prospects WHERE id=?", (pid,)).fetchone()[0]
    ensure_batch_requests()
    cb = batch_callback(oid, lid)
    fake_hub['status'][cb] = 'no'
    res = consume_approvals()
    assert len(res['consumed']) == 1 and res['consumed'][0]['statut'] == 'refuse'
    assert spy_run_relances == []
    with get_conn() as c:
        assert c.execute("SELECT statut FROM relance_batches WHERE callback_id=?",
                         (cb,)).fetchone()[0] == 'refuse'
    # Lot refusé à l'identique → ne pas re-demander
    from core.relance_batch_validator import ensure_batch_requests as ensure2
    assert ensure2()['requests'] == []