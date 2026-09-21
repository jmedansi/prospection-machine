# -*- coding: utf-8 -*-
"""
core/objectif_registry.py — rattachement des ingests (scraping Maps, toutes sources)
à un objectif v2.

L'utilisateur choisit l'objectif AVANT d'enregistrer des leads. Le scraping reçoit
`--objectif <nom|id>` : l'objectif est retrouvé (ou créé s'il n'existe pas) une fois,
puis chaque lead enrichi est inséré dans `prospects` avec sa source.
Aucune logique d'envoi ici — ingestion uniquement.
"""
from database import objectifs as objectifs_repo
from database import prospects as prospects_repo


def resolve_or_create_objectif(nom_or_id):
    """Résout un objectif (par id ou par nom) et le crée s'il est absent.

    Retourne (objectif_id, objectif_nom) ou None si impossible (nom vide,
    objectif introuvable ET création impossible).
    """
    s = str(nom_or_id or '').strip()
    if not s:
        return None

    obj = None
    if s.isdigit():
        try:
            obj = objectifs_repo.get_objectif(int(s))
        except Exception:
            obj = None
    if not obj:
        obj = objectifs_repo.get_objectif_by_nom(s)
    if not obj:
        res = objectifs_repo.create_objectif(s)
        obj = res.get('objectif') if res.get('success') else None
    if not obj:
        return None
    if obj.get('statut') == 'archive':
        return None
    return obj['id'], obj['nom']


def import_lead_as_prospect(objectif_id, lead, source='scraping', data_extra_extra=None) -> dict:
    """Insère un lead issus d'un ingest (scraping/ADS/...) dans un objectif v2.

    `lead` = dict enrichi (mêmes clés que scraper/main.py `_enrichir_place`).
    Retourne le résultat de `insert_prospect` (statut_dedupe : created/doublon/
    suppression_list). Aucune levée d'exception si possible.
    """
    nom = (lead.get('nom') or '').strip()
    email = (lead.get('email') or '').strip()
    if not nom and not email:
        return {'success': False, 'statut_dedupe': None, 'error': 'Lead sans nom ni email'}

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

    return prospects_repo.insert_prospect(
        objectif_id,
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