# -*- coding: utf-8 -*-
"""
core/objectif_registry.py — rattachement des ingests (scraping Maps, toutes sources)
à une liste v2 (dans une campagne).

Le scraping reçoit `--objectif <nom|id>` (compat : la campagne porte le nom) :
la campagne est retrouvée (ou créée), sa liste par défaut est utilisée (ou créée),
puis chaque lead enrichi est inséré dans `prospects`. Aucune logique d'envoi ici —
ingestion uniquement.
"""
from database import campagnes as campagnes_repo
from database import prospects as prospects_repo
from database import listes as listes_repo
from database.connection import get_conn


def resolve_or_create_campagne(nom_or_id):
    """Résout une campagne (par id ou par nom) et la crée si absente.

    Retourne (campagne_id, campagne_nom) ou None si impossible.
    """
    s = str(nom_or_id or '').strip()
    if not s:
        return None

    camp = None
    if s.isdigit():
        try:
            camp = campagnes_repo.get_campagne(int(s))
        except Exception:
            camp = None
    if not camp:
        camp = campagnes_repo.get_campagne_by_nom(s)
    if not camp:
        res = campagnes_repo.create_campagne(s)
        camp = res.get('campagne') if res.get('success') else None
    if not camp:
        return None
    if camp.get('statut') == 'archive':
        return None
    return camp['id'], camp['nom']


# Compat : le nom « objectif » reste accepté (alias strict du nouveau nom).
resolve_or_create_objectif = resolve_or_create_campagne


def get_or_create_liste(campagne_id: int, nom: str | None = None) -> int | None:
    """Liste par défaut d'une campagne (première liste active), créée si absente."""
    campagne_id = int(campagne_id)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM listes WHERE campagne_id = ? AND statut = 'actif' ORDER BY id LIMIT 1",
            (campagne_id,),
        ).fetchone()
        if row:
            return row['id']
    camp = campagnes_repo.get_campagne(campagne_id)
    if not camp:
        return None
    res = listes_repo.create_liste(campagne_id, nom or camp['nom'])
    if res.get('success'):
        return res['liste']['id']
    return None


def import_lead_as_prospect(campagne_id, lead, source='scraping', data_extra_extra=None,
                            liste_id=None) -> dict:
    """Insère un lead issu d'un ingest (scraping/ADS/...) dans la liste cible.

    `liste_id` : liste cible explicite ; sinon la liste par défaut de la campagne
    (créée à la volée). `lead` = dict enrichi (mêmes clés que scraper/main.py
    `_enrichir_place`). Retourne le résultat de `insert_prospect` (statut_dedupe :
    created/doublon/suppression_list) ou `updated` quand le doublon existait dans
    une autre campagne (objectif différent → enrichissement, pas de création).
    Aucune levée d'exception si possible.
    """
    nom = (lead.get('nom') or '').strip()
    email = (lead.get('email') or '').strip()
    if not nom and not email:
        return {'success': False, 'statut_dedupe': None, 'error': 'Lead sans nom ni email'}

    if not liste_id:
        liste_id = get_or_create_liste(campagne_id)

    secteur = (lead.get('secteur') or lead.get('category') or '').strip()
    extra = {
        'lien_maps': lead.get('lien_maps'),
        'logo_url': lead.get('logo_url'),
        'email_2': lead.get('email_2'),
        'email_source': lead.get('email_source'),
        'statut_email': lead.get('statut_email'),
        'mot_cle': lead.get('mot_cle'),
        'pays': lead.get('pays'),
        'date_scraping': lead.get('date_scraping'),
    }
    if isinstance(data_extra_extra, dict):
        extra.update(data_extra_extra)
    extra = {k: v for k, v in extra.items() if v not in (None, '')}

    # Objectif DIFFÉRENT (doublon dans une autre campagne) → enrichir l'existant,
    # jamais créer de doublon cross-campagne.
    from database.connection import get_conn
    from database.dedup import find_duplicate_cross_campagne
    import database.prospects as _prospects
    with get_conn() as conn:
        dup = find_duplicate_cross_campagne(
            conn, exclude_campagne_id=campagne_id,
            email=email, telephone=lead.get('telephone'), site_web=lead.get('site_web'),
        )
        if not dup:
            return prospects_repo.insert_prospect(
                liste_id,
                nom=nom,
                prenom=lead.get('prenom') or '',
                email=email,
                telephone=lead.get('telephone'),
                entreprise=lead.get('entreprise'),
                site_web=lead.get('site_web'),
                adresse=lead.get('adresse'),
                ville=lead.get('ville'),
                secteur=secteur,
                rating=lead.get('rating'),
                nb_avis=lead.get('nb_avis'),
                source=source,
                data_extra=extra,
            )
        if dup.get('ne_plus_contacter') or _prospects._is_in_suppression_list(conn, email):
            return {'success': False, 'prospect_id': dup['id'],
                    'statut_dedupe': 'suppression_list',
                    'error': 'Prospect opposé ou dans la liste de suppression'}
        _prospects.enrich_prospect(
            conn, dup['id'], nom=nom, prenom=lead.get('prenom'), email=email,
            telephone=lead.get('telephone'), site_web=lead.get('site_web'),
            nb_avis=lead.get('nb_avis'), data_extra=extra,
        )
        conn.commit()
    return {'success': True, 'prospect_id': dup['id'], 'statut_dedupe': 'updated'}