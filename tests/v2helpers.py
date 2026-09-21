# -*- coding: utf-8 -*-
"""
tests/v2helpers.py — Aides communes aux tests v2 (modèle Campagne → Liste → Prospect).

Fournit :
  - resolve_campagne(nom, envoi_auto, validation_telegram, ...) → id campagne
  - make_liste(campagne_id, nom=None) → id liste
  - add_prospect(campagne_id, email, ...) → id prospect (dans la liste par défaut)
"""
from database import prospects as prospects_repo
from core.objectif_registry import resolve_or_create_campagne, get_or_create_liste


def resolve_campagne(nom='Refonte site web', envoi_auto=1, validation_telegram=0, **kwargs):
    cid, _nom = resolve_or_create_campagne(nom)
    from database.connection import get_conn
    with get_conn() as c:
        c.execute(
            "UPDATE campagnes SET envoi_auto=?, validation_telegram=? WHERE id=?",
            (envoi_auto, validation_telegram, cid),
        )
        c.commit()
    return cid


def make_liste(campagne_id, nom=None):
    return get_or_create_liste(campagne_id, nom)


def add_prospect(campagne_id, email='contact@dupont.fr', oppose=False, ecarte=False,
                 no_email=False, liste_id=None, nom='Boulangerie Dupont'):
    lid = liste_id or make_liste(campagne_id)
    pid = prospects_repo.insert_prospect(
        lid,
        nom=nom,
        email='' if no_email else email,
        entreprise=nom,
        secteur='Boulangerie',
    )['prospect_id']
    from database.connection import get_conn
    with get_conn() as c:
        if oppose:
            c.execute("UPDATE prospects SET ne_plus_contacter=1, statut='ne_plus_contacter' WHERE id=?", (pid,))
        if ecarte:
            c.execute("UPDATE prospects SET ecarte=1 WHERE id=?", (pid,))
        c.commit()
    return pid