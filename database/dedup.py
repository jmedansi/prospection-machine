# -*- coding: utf-8 -*-
"""
database/dedup.py — Clés d'unicité normalisées et recherche de doublons v2.

Règle d'unicité (validée produit) :
  - Scope = campagne (l'« objectif »).
  - Dans LA MÊME campagne : un prospect (même email OU même site_web OU même
    téléphone normalisés) est un doublon → refusé à l'ingestion.
  - Entre DEUX campagnes différentes (objectifs différents) : le doublon est
    enrichi sur l'existant (aucune création) — géré par import_lead_as_prospect.
"""
import re
from email.utils import parseaddr


def normalize_email(email):
    """Retire les balises « Nom <x@y.fr> », minuscules, strip."""
    if not email:
        return ''
    email = (email or '').strip().lower()
    real = parseaddr(email)[1] or email
    return real.strip().lower()


def normalize_site(site):
    """Normalise une URL de site : minuscules, sans schéma/www, sans chemin,
    sans paramètres/ancres, sans slash terminal. Clé naturelle des commerces
    (on réduit au domaine : monresto.fr et monresto.fr/page?utm=1 → monresto.fr)."""
    if not site:
        return ''
    s = (site or '').strip().lower()
    s = s.split('?')[0].split('#')[0]
    s = re.sub(r'^[a-z][a-z0-9+.-]*://', '', s)
    if s.startswith('www.'):
        s = s[4:]
    s = s.split('/')[0]
    return s.rstrip('.')


def normalize_tel(tel):
    """Téléphone réduit aux chiffres, préfixe 0/00/33 ramené à une forme unique."""
    if not tel:
        return ''
    t = re.sub(r'\D', '', str(tel))
    if t.startswith('00'):
        t = t[2:]
    if t.startswith('33') and len(t) > 10:
        t = t[2:]
    if t.startswith('0') and len(t) == 10:
        t = t[1:]
    return t


def find_duplicate_in_campagne(conn, campagne_id, *, email='', telephone='', site_web='',
                               exclude_id=None):
    """Cherche un doublon DANS la campagne (même objectif → refus).

    Retourne la ligne prospect (dict) ou None. Priorité de robustesse :
    site_web (clé naturelle commerce) > email > téléphone.
    """
    target_site = normalize_site(site_web)
    target_email = normalize_email(email)
    target_tel = normalize_tel(telephone)

    rows = conn.execute(
        """
        SELECT p.id, p.email, p.telephone, p.site_web
        FROM prospects p JOIN listes l ON p.liste_id = l.id
        WHERE l.campagne_id = ? AND l.statut = 'actif'
        """, (campagne_id,)
    ).fetchall()

    for r in rows:
        if exclude_id and r['id'] == exclude_id:
            continue
        if target_site and normalize_site(r['site_web']) == target_site:
            return dict(r)
    for r in rows:
        if exclude_id and r['id'] == exclude_id:
            continue
        if target_email and normalize_email(r['email']) == target_email:
            return dict(r)
    for r in rows:
        if exclude_id and r['id'] == exclude_id:
            continue
        if target_tel and normalize_tel(r['telephone']) == target_tel:
            return dict(r)
    return None


def find_duplicate_cross_campagne(conn, exclude_campagne_id=None, *, email='', telephone='',
                                  site_web=''):
    """Cherche un doublon dans les AUTRES campagnes (objectifs différents → update).

    Retourne la ligne prospect (dict, avec liste_id) ou None.
    """
    target_site = normalize_site(site_web)
    target_email = normalize_email(email)
    target_tel = normalize_tel(telephone)

    query = """
        SELECT p.id, p.email, p.telephone, p.site_web, l.campagne_id,
               p.ne_plus_contacter
        FROM prospects p JOIN listes l ON p.liste_id = l.id
        WHERE l.statut = 'actif'
    """
    params = []
    if exclude_campagne_id:
        query += " AND l.campagne_id != ?"
        params.append(exclude_campagne_id)
    rows = conn.execute(query, params).fetchall()

    for r in rows:
        if target_site and normalize_site(r['site_web']) == target_site:
            return dict(r)
    for r in rows:
        if target_email and normalize_email(r['email']) == target_email:
            return dict(r)
    for r in rows:
        if target_tel and normalize_tel(r['telephone']) == target_tel:
            return dict(r)
    return None