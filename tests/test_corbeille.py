# -*- coding: utf-8 -*-
"""
Tests v2 — la Corbeille comme POUBELLE.

Contrats :
  1. chaque liste a sa propre poubelle (`type='corbeille'`, `corbeille_de`) ;
  2. une poubelle n'est JAMAIS une liste d'envoi : exclue de `list_listes`,
     de `list_prospects` (hors ciblage explicite), des stats et de la liste
     par défaut d'une campagne ;
  3. la Corbeille de campagne est une VUE qui agrège toutes ses poubelles ;
   4. les déchets (bounces / désinscriptions) atterrissent dans la poubelle de
      LEUR liste via `unlink_prospects` ;
   5. retour arrière POSSIBLE : `restore_prospects()` remet les prospects dans la
      liste source (`corbeille_de`), et impose une `target_liste_id` pour les
      poubelles héritées dont l'origine est perdue.
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


def _mk_liste(cid, nom):
    """Crée UNE liste (≠ `get_or_create_liste` qui renvoie la première liste existante)."""
    from database.listes import create_liste
    res = create_liste(cid, nom)
    assert res.get('success'), res
    return res['liste']['id']


def _seed(cid, lid, idx):
    from database import prospects_repo
    return prospects_repo.insert_prospect(
        lid, nom=f'Agence {idx}', email=f'contact{idx}@exemple.fr',
        entreprise=f'Agence {idx}', secteur='Agence')['prospect_id']


def test_chaque_liste_a_sa_poubelle(tmp_db):
    from core.objectif_registry import get_or_create_liste, resolve_or_create_campagne
    from database.listes import (corbeille_counts, get_or_create_corbeille_liste,
                                 list_listes, unlink_prospects)

    cid, _ = resolve_or_create_campagne('Agences IA')
    lid_a = _mk_liste(cid, 'Liste A')
    lid_b = _mk_liste(cid, 'Liste B')
    p = _seed(cid, lid_a, 1)

    assert unlink_prospects(lid_a, [p])['moved'] == 1
    cb_a = get_or_create_corbeille_liste(lid_a)

    from database.connection import get_conn
    with get_conn() as c:
        row = c.execute("SELECT type, corbeille_de, campagne_id FROM listes WHERE id=?",
                        (cb_a,)).fetchone()
        assert row['type'] == 'corbeille'
        assert row['corbeille_de'] == lid_a
        assert row['campagne_id'] == cid
        # le prospect est bien rangé dedans
        assert c.execute("SELECT liste_id FROM prospects WHERE id=?", (p,)).fetchone()['liste_id'] == cb_a

    # Une poubelle par liste : celles de A et de B sont distinctes
    cb_b = get_or_create_corbeille_liste(lid_b)
    assert cb_b != cb_a

    # Idempotent : relancer ne crée pas de seconde poubelle
    assert get_or_create_corbeille_liste(lid_a) == cb_a

    # Les poubelles ne sont PAS des listes : exclues, mais comptées par source
    ids = {l['id'] for l in list_listes(cid)}
    assert lid_a in ids and lid_b in ids
    assert cb_a not in ids and cb_b not in ids
    infos = {l['id']: l for l in list_listes(cid)}
    assert infos[lid_a]['corbeille_id'] == cb_a
    assert infos[lid_a]['nb_corbeille'] == 1
    assert infos[lid_b]['corbeille_id'] == cb_b
    assert infos[lid_b]['nb_corbeille'] == 0

    counts = corbeille_counts(cid)
    assert counts[cid]['total'] == 1
    assert counts[cid]['listes'].get(lid_a) == 1
    assert counts[cid]['listes'].get(lid_b) == 0


def test_la_vue_campagne_agrege_toutes_ses_poubelles(tmp_db):
    from core.objectif_registry import get_or_create_liste, resolve_or_create_campagne
    from database import prospects_repo
    from database.listes import unlink_prospects

    cid, _ = resolve_or_create_campagne('Agences SEO')
    lid_a = _mk_liste(cid, 'Liste A')
    lid_b = _mk_liste(cid, 'Liste B')
    pa, pb = _seed(cid, lid_a, 1), _seed(cid, lid_b, 2)
    unlink_prospects(lid_a, [pa])
    unlink_prospects(lid_b, [pb])

    # Hors paramètre : les poubelles sont hors des vues opérationnelles
    res = prospects_repo.list_prospects(campagne_id=cid)
    assert res['total'] == 0

    # corbeille='1' → vue « 🗑 Corbeille » de la campagne (agrégée)
    vue = prospects_repo.list_prospects(campagne_id=cid, corbeille='1')
    assert vue['total'] == 2
    from database.connection import get_conn
    with get_conn() as c:
        for lead in vue['leads']:
            assert c.execute("SELECT type FROM listes WHERE id=?",
                             (lead['liste_id'],)).fetchone()['type'] == 'corbeille'

    # Un liste_id explicite reste non filtré (ciblage direct sur la poubelle)
    from database.listes import get_or_create_corbeille_liste
    cb_a = get_or_create_corbeille_liste(lid_a)
    ciblage = prospects_repo.list_prospects(liste_id=cb_a)
    assert ciblage['total'] == 1


def test_les_stats_ne_comptent_jamais_les_dechets(tmp_db):
    from core.objectif_registry import get_or_create_liste, resolve_or_create_campagne
    from database.listes import unlink_prospects
    from database.stats import _stats_v2
    from database.connection import get_conn

    cid, _ = resolve_or_create_campagne('Agences UX')
    lid = _mk_liste(cid, 'Liste UX')
    pa, pb = _seed(cid, lid, 1), _seed(cid, lid, 2)

    with get_conn() as c:
        assert _stats_v2(c, cid)['leads_scrapes'] == 2

    unlink_prospects(lid, [pb])
    with get_conn() as c:
        assert _stats_v2(c, cid)['leads_scrapes'] == 1


def test_la_liste_par_defaut_ne_peut_etre_une_poubelle(tmp_db):
    from core.objectif_registry import get_or_create_liste, resolve_or_create_campagne
    from database import listes as listes_repo
    from database.listes import get_or_create_corbeille_liste, unlink_prospects
    from database.connection import get_conn

    cid, _ = resolve_or_create_campagne('Agences Dev')
    lid = _mk_liste(cid, 'Liste Dev')
    p = _seed(cid, lid, 1)
    unlink_prospects(lid, [p])
    cb = get_or_create_corbeille_liste(lid)

    # La liste source disparaît : il ne reste QUE la poubelle dans la campagne.
    # `get_or_create_liste` doit en recréer une normale, jamais renvoyer la poubelle.
    assert listes_repo.delete_liste(lid)['success']
    new = get_or_create_liste(cid)
    assert new and new != cb
    with get_conn() as c:
        assert c.execute("SELECT type FROM listes WHERE id=?", (new,)).fetchone()['type'] == 'normal'


def test_le_retrait_d_une_poubelle_ne_cree_pas_de_poubelle_de_poubelle(tmp_db):
    from core.objectif_registry import get_or_create_liste, resolve_or_create_campagne
    from database.listes import get_or_create_corbeille, unlink_prospects

    cid, _ = resolve_or_create_campagne('Agences WP')
    lid = _mk_liste(cid, 'Liste WP')
    p = _seed(cid, lid, 1)
    unlink_prospects(lid, [p])
    from database.listes import get_or_create_corbeille_liste
    cb = get_or_create_corbeille_liste(lid)

    # Retirer quelqu'un DÉJÀ dans la poubelle → corbeille orpheline de campagne
    res = unlink_prospects(cb, [p])
    assert res['success']
    assert res['corbeille_id'] == get_or_create_corbeille(cid)
    assert res['corbeille_id'] != cb


def test_la_restauration_remet_dans_la_liste_source(tmp_db):
    from core.objectif_registry import resolve_or_create_campagne
    from database import listes as listes_repo, prospects_repo
    from database.listes import get_or_create_corbeille_liste, unlink_prospects
    from database.stats import _stats_v2
    from database.connection import get_conn

    cid, _ = resolve_or_create_campagne('Agences Restauration')
    lid = _mk_liste(cid, 'Liste R')
    p = _seed(cid, lid, 1)
    _seed(cid, lid, 2)
    unlink_prospects(lid, [p])
    cb = get_or_create_corbeille_liste(lid)

    with get_conn() as c:
        assert _stats_v2(c, cid)['leads_scrapes'] == 1
    assert prospects_repo.list_prospects(liste_id=lid)['total'] == 1
    assert prospects_repo.list_prospects(liste_id=cb)['total'] == 1

    # Cible par défaut = la liste source mémorisée par `corbeille_de`
    res = listes_repo.restore_prospects(cb, [p])
    assert res['success'] and res['moved'] == 1
    assert res['target_liste_id'] == lid

    assert prospects_repo.list_prospects(liste_id=lid)['total'] == 2
    assert prospects_repo.list_prospects(liste_id=cb)['total'] == 0
    with get_conn() as c:
        assert c.execute("SELECT liste_id FROM prospects WHERE id=?", (p,)).fetchone()['liste_id'] == lid
        assert _stats_v2(c, cid)['leads_scrapes'] == 2
    # La poubelle existe toujours (vide) et reste hors des listes d'envoi
    infos = {l['id']: l for l in listes_repo.list_listes(cid)}
    assert cb not in infos and infos[lid]['nb_corbeille'] == 0

    # Idempotent / inoffensif sur une poubelle vide
    assert listes_repo.restore_prospects(cb, [p])['moved'] == 0


def test_les_poubelles_heritees_imposent_une_liste_cible(tmp_db):
    from core.objectif_registry import resolve_or_create_campagne
    from database import listes as listes_repo
    from database.listes import get_or_create_corbeille, get_or_create_corbeille_liste, unlink_prospects
    from database.connection import get_conn

    cid, _ = resolve_or_create_campagne('Agences Héritage')
    lid = _mk_liste(cid, 'Liste H')
    p = _seed(cid, lid, 1)
    unlink_prospects(lid, [p])
    cb = get_or_create_corbeille_liste(lid)

    # Poubelle héritée : origine perdue (4 corbeilles legacy sont dans ce cas)
    with get_conn() as c:
        c.execute("UPDATE listes SET corbeille_de = NULL WHERE id=?", (cb,))
        c.commit()

    res = listes_repo.restore_prospects(cb, [p])
    assert not res['success'] and res['error'] == 'liste_cible_requise'

    ok = listes_repo.restore_prospects(cb, [p], target_liste_id=lid)
    assert ok['success'] and ok['moved'] == 1
    with get_conn() as c:
        assert c.execute("SELECT liste_id FROM prospects WHERE id=?", (p,)).fetchone()['liste_id'] == lid


def test_la_restauration_refuse_les_cibles_invalides(tmp_db):
    from core.objectif_registry import resolve_or_create_campagne
    from database import listes as listes_repo
    from database.listes import get_or_create_corbeille_liste, unlink_prospects

    cid, _ = resolve_or_create_campagne('Agences Cibles')
    cid2, _ = resolve_or_create_campagne('Autre campagne')
    lid = _mk_liste(cid, 'Liste C')
    p = _seed(cid, lid, 1)
    unlink_prospects(lid, [p])
    cb = get_or_create_corbeille_liste(lid)

    # Une liste normale n'est pas une poubelle
    res = listes_repo.restore_prospects(lid, [p])
    assert not res['success'] and 'pas une poubelle' in res['error']

    # On ne repasse pas par une autre poubelle
    res = listes_repo.restore_prospects(cb, [p], target_liste_id=cb)
    assert not res['success']

    # Pas de cible dans une autre campagne
    lid2 = _mk_liste(cid2, 'Liste étrangère')
    res = listes_repo.restore_prospects(cb, [p], target_liste_id=lid2)
    assert not res['success'] and 'autre campagne' in res['error']

    # Cible inexistante
    res = listes_repo.restore_prospects(cb, [p], target_liste_id=999999)
    assert not res['success'] and 'introuvable' in res['error']

    # Sélection vide
    res = listes_repo.restore_prospects(cb, [])
    assert not res['success']
