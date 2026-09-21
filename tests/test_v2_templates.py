# -*- coding: utf-8 -*-
"""
Tests v2 — registre de templates, humanisation IA et moteur d'envoi initial.

Base SQLite temporaire. Aucun email réel : dry_run + verrous.
"""
import pytest

import database.connection as conn_mod
from database.schema import init_db, migrate_v2_schema


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "prospection_tpl_test.db"
    monkeypatch.setattr(conn_mod, 'DB_PATH', db_path)
    monkeypatch.setattr('database.schema.connection.DB_PATH', db_path)
    init_db()
    migrate_v2_schema()
    yield db_path


def _objectif(nom='Refonte site web'):
    from database import campagnes_repo
    return campagnes_repo.create_campagne(nom)['campagne']['id']


def _prospect(oid, email='contact@dupont.fr', statut='qualifie', site_web='https://dupont.fr'):
    from core.objectif_registry import get_or_create_liste
    from database import prospects_repo
    lid = get_or_create_liste(oid)
    pid = prospects_repo.insert_prospect(lid, nom='Boulangerie Dupont', email=email,
                                         prenom='M. Dupont', entreprise='Boulangerie Dupont',
                                         secteur='Boulangerie', site_web=site_web)['prospect_id']
    if statut != 'qualifie':
        from core.state_machine import transition_prospect
        transition_prospect(pid, statut, reason='test')
    return pid


def _del_seed_templates():
    from envoi import template_registry as tr
    for t in tr.get_templates(include_inactifs=True):
        if t['campagne_id'] is None:
            tr.delete(t['id'])


# ─── Registre de templates ─────────────────────────────────────────────────────

def test_get_templates_filtre_actif_et_objectif(tmp_db):
    from envoi import template_registry as tr
    _del_seed_templates()
    oid = _objectif()
    tr.add_or_update(campagne_id=oid, nom='Initial obj', objet='O {{prenom}}', corps='C',
                     position=0, delai_jours=0)
    tr.add_or_update(nom='Générique', objet='G', corps='C', position=1, delai_jours=3)
    tr.add_or_update(nom='Désactivé', objet='X', corps='C', position=2)
    tid = tr.get_templates(campagne_id=oid)[-1]['id']
    tr.set_actif(tid, False)

    temps = tr.get_templates(campagne_id=oid)
    noms = [t['nom'] for t in temps]
    assert noms == ['Initial obj', 'Générique']  # dédié before générique, inactif exclu

    # un autre objectif ne voit QUE le générique
    oid2 = _objectif('Autre objectif')
    noms2 = [t['nom'] for t in tr.get_templates(campagne_id=oid2)]
    assert noms2 == ['Générique']


def test_get_step_priorite_objectif_puis_generique(tmp_db):
    from envoi import template_registry as tr
    oid = _objectif()
    tr.add_or_update(campagne_id=oid, nom='Dédié', objet='Dédié {{prenom}}', corps='c', position=0)
    step = tr.get_step(oid, position=0)
    assert step['nom'] == 'Dédié'
    # sans template dédié → générique (seed position 0)
    oid2 = _objectif('B')
    step2 = tr.get_step(oid2, position=0)
    assert step2['campagne_id'] is None


def test_render_variables(tmp_db):
    from envoi import template_registry as tr
    oid = _objectif()
    pid = _prospect(oid)
    from database import prospects_repo
    p = prospects_repo.get_prospect(pid)
    assert tr.render('Bonjour {{prenom}} ({{entreprise}}, {{secteur}})', p) == \
        'Bonjour M. Dupont (Boulangerie Dupont, Boulangerie)'
    # var inconnue restée telle quelle
    assert tr.render('{{frufru}}', p) == '{{frufru}}'


def test_render_template_rapporte_vars_inconnues(tmp_db):
    from envoi import template_registry as tr
    oid = _objectif()
    pid = _prospect(oid)
    from database import prospects_repo
    p = prospects_repo.get_prospect(pid)
    out = tr.render_template({'objet': '{{prenom}}', 'corps': '{{frufru}}'}, p)
    assert out['objet'] == 'M. Dupont'
    assert out['vars_inconnues'] == ['frufru']


def test_unknown_variables(tmp_db):
    from envoi import template_registry as tr
    assert tr.unknown_variables({'objet': '{{prenom}} {{inconnu}}', 'corps': '{{corps}}'}) == ['inconnu']
    assert tr.unknown_variables({'objet': '{{prenom}}', 'corps': 'x'}) == []


def test_seed_generique_sans_placeholder(tmp_db):
    """Le template générique (pos 0) rend un corps réel, jamais {{corps}} littéral."""
    from envoi import template_registry as tr
    oid = _objectif()
    pid = _prospect(oid)
    from database import prospects_repo
    p = prospects_repo.get_prospect(pid)
    step = tr.get_step(oid, position=0)
    out = tr.render_template(step, p)
    assert '{{corps}}' not in out['corps']
    assert '{{corps}}' not in out['objet']
    assert 'Jean-Marc' in out['corps']


def test_render_placeholder_corps_substitue(tmp_db):
    from envoi import template_registry as tr
    oid = _objectif()
    pid = _prospect(oid)
    from database import prospects_repo
    p = prospects_repo.get_prospect(pid)
    out = tr.render_template({'objet': 'O', 'corps': 'Bonjour {{prenom}},\n\n{{corps}}'}, p)
    assert out['corps'] == 'Bonjour M. Dupont,\n\n' + tr.render(tr._DEFAULT_BODY_CONTENT, p)
    assert '{{corps}}' not in out['corps']


def test_render_prenom_fallback_sur_entite(tmp_db):
    """Prospect sans prénom → saluer par le nom de l'entité, pas « Bonjour , »."""
    from envoi import template_registry as tr
    oid = _objectif()
    from core.objectif_registry import get_or_create_liste
    from database import prospects_repo
    lid = get_or_create_liste(oid)
    pid = prospects_repo.insert_prospect(lid, nom='BRAND ELOQUENCE', email='c@be.fr',
                                         secteur='agence web')['prospect_id']
    p = prospects_repo.get_prospect(pid)
    assert tr.render('Bonjour {{prenom}},', p) == 'Bonjour BRAND ELOQUENCE,'
    assert tr._ctx_for(p)['entreprise'] == 'BRAND ELOQUENCE'


# ─── Humanisation IA ───────────────────────────────────────────────────────────

def test_humanize_sans_cle_groq_retourne_original(tmp_db, monkeypatch):
    from envoi import humanize
    monkeypatch.delenv('GROQ_API_KEY', raising=False)
    monkeypatch.delenv('GROQ_API_KEY_2', raising=False)
    r = humanize.humanize_email('Objet', 'Corps de test', dry_run=False)
    assert r == {'objet': 'Objet', 'corps': 'Corps de test', 'humanise': False}


def test_humanize_dry_run(tmp_db):
    from envoi import humanize
    r = humanize.humanize_email('O', 'C', dry_run=True)
    assert r['humanise'] is False


def test_extract_json_tolere_balises():
    from envoi.humanize import extract_json
    assert extract_json('Voici :\n```json\n{"objet":"O","corps":"C"}\n```') == {'objet': 'O', 'corps': 'C'}
    assert extract_json('{"objet":"O"}') == {'objet': 'O'}
    assert extract_json('rien du tout') == {}


# ─── Moteur d'envoi initial ────────────────────────────────────────────────────

def test_send_initial_dry_run_succes_sans_effet(tmp_db):
    from envoi import sequence_engine as seq
    oid = _objectif()
    pid = _prospect(oid)
    r = seq.send_initial(oid, pid, dry_run=True)
    assert r['success']
    assert r['statut'] == 'dry_run'
    # pas de transition, pas d'event
    from database import prospects_repo
    p = prospects_repo.get_prospect(pid)
    assert p['statut'] == 'qualifie'
    assert all(e['event_type'] != 'initial' for e in p['events'])


def test_send_initial_verrous(tmp_db):
    from envoi import sequence_engine as seq
    oid = _objectif()
    pid = _prospect(oid)
    assert not seq.send_initial(999, pid, dry_run=True)['success']
    assert not seq.send_initial(oid, 99999, dry_run=True)['success']

    # déjà en flux
    pid2 = _prospect(oid, email='bis@dupont.fr', statut='en_sequence', site_web='https://bis.dupont.fr')
    r = seq.send_initial(oid, pid2, dry_run=True)
    assert not r['success'] and r['statut'] == 'deja_en_flux'

    # sans email
    from database import prospects_repo
    from core.objectif_registry import get_or_create_liste
    pid3 = prospects_repo.insert_prospect(get_or_create_liste(oid), nom='Sans mail')['prospect_id']
    r = seq.send_initial(oid, pid3, dry_run=True)
    assert not r['success'] and r['statut'] == 'pas_email'

    # sans template position 0
    from envoi import template_registry as tr
    for t in tr.get_templates(campagne_id=oid, include_inactifs=True):
        tr.delete(t['id'])
    r = seq.send_initial(oid, pid, dry_run=True)
    assert not r['success'] and r['statut'] == 'pas_template'


def test_send_initial_envoi_effectif_sur_boite_test(tmp_db):
    from envoi import sequence_engine as seq
    from database.connection import get_conn
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO mailboxes
               (label, domaine, email, smtp_host, smtp_port, smtp_user, smtp_pass,
                backend, quota_jour, usage_jour, campagne_pool)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            ('Zoho test', 'zoho.fr', 'test@zoho.fr', 'smtp.invalid', 587, 'test@zoho.fr',
             'pw', 'smtp', 40, 0, '*'),
        )
        conn.commit()
    oid = _objectif()
    pid = _prospect(oid)
    r = seq.send_initial(oid, pid, dry_run=False)
    # host invalide → échec d'envoi, pas de crash, pas de transition
    assert not r['success']
    assert r['statut'] == 'erreur_inattendue'
    from database import prospects_repo
    assert prospects_repo.get_prospect(pid)['statut'] == 'qualifie'

    # après connexion OK simulée (dry_run), dry_run ne touche pas la machine
    r2 = seq.send_initial(oid, pid, dry_run=True)
    assert r2['success'] and r2['statut'] == 'dry_run'