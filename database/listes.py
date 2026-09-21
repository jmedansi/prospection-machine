# -*- coding: utf-8 -*-
"""
database/listes.py — Repo des cartes/listes de prospects (spec §8).

Une liste est l'unité opérationnelle qui porte les prospects : un scraping,
un import ou un secteur = une liste. Elle appartient à une et une seule
campagne, qui porte la configuration du cycle de vie partagée.
"""
import json
from datetime import datetime

from database.connection import get_conn, logger

ALLOWED_FIELDS = {
    'nom', 'description', 'secteur', 'source', 'statut', 'note',
    'icone', 'couleur', 'objectif',
}


def require_campagne(campagne_id: int) -> bool:
    with get_conn() as conn:
        return conn.execute("SELECT id FROM campagnes WHERE id = ?", (campagne_id,)).fetchone() is not None


def create_liste(campagne_id: int, nom: str, description: str = '', **kwargs) -> dict:
    """Crée une liste dans une campagne. Le nom est requis."""
    nom = (nom or '').strip()
    if not nom:
        return {'success': False, 'error': 'Le nom de la liste est obligatoire'}
    if kwargs.get('skip_campagne_check') is None and not require_campagne(campagne_id):
        return {'success': False, 'error': 'Campagne introuvable'}
    try:
        with get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO listes (campagne_id, nom, description, secteur, source, note, icone, couleur, objectif, statut)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    campagne_id,
                    nom,
                    str(description or ''),
                    str(kwargs.get('secteur') or ''),
                    str(kwargs.get('source') or 'import'),
                    str(kwargs.get('note') or ''),
                    str(kwargs.get('icone') or '📋'),
                    str(kwargs.get('couleur') or '#6366f1'),
                    str(kwargs.get('objectif') or 'general'),
                    str(kwargs.get('statut') or 'actif'),
                ),
            )
            liste_id = cur.lastrowid
            conn.commit()
            logger.info("Liste créée : #%s « %s » (campagne #%s)", liste_id, nom, campagne_id)
            return {'success': True, 'liste': get_liste(liste_id)}
    except Exception as e:
        logger.error("Erreur création liste « %s » : %s", nom, e)
        return {'success': False, 'error': str(e)}


def get_liste(liste_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM listes WHERE id = ?", (liste_id,)).fetchone()
        return _row_to_dict(row)


def list_listes(campagne_id: int | None = None, include_archives: bool = False,
                statut: str | None = None, search: str | None = None) -> list:
    """Liste les listes (optionnellement d'une seule campagne) avec comptages."""
    with get_conn() as conn:
        sql = """SELECT l.*, c.nom AS campagne_nom,
                        (SELECT COUNT(*) FROM prospects p WHERE p.liste_id = l.id) AS nb_leads,
                        (SELECT MAX(p.updated_at) FROM prospects p WHERE p.liste_id = l.id) AS derniere_touche
                 FROM listes l
                 JOIN campagnes c ON c.id = l.campagne_id """
        where = []
        params = []
        if campagne_id is not None:
            where.append("l.campagne_id = ?")
            params.append(campagne_id)
        if statut is not None:
            where.append("l.statut = ?")
            params.append(statut)
        elif not include_archives:
            where.append("l.statut = 'actif'")
        if search:
            where.append("(l.nom LIKE ? OR l.secteur LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like])
        if where:
            sql += "WHERE " + " AND ".join(where) + " "
        sql += "ORDER BY l.nom ASC"
        rows = conn.execute(sql, params).fetchall()
        result = []
        for r in rows:
            d = _row_to_dict(r)
            d['nb_leads'] = r['nb_leads']
            d['statut_breakdown'] = _statut_breakdown(conn, r['id'])
            result.append(d)
        return result


def _statut_breakdown(conn, liste_id: int) -> dict:
    rows = conn.execute(
        "SELECT statut, COUNT(*) AS n FROM prospects WHERE liste_id = ? GROUP BY statut",
        (liste_id,),
    ).fetchall()
    return {r['statut']: r['n'] for r in rows}


def update_liste(liste_id: int, **kwargs) -> dict:
    updates = {k: v for k, v in kwargs.items() if k in ALLOWED_FIELDS}
    if not updates:
        return {'success': False, 'error': 'Aucun champ valide à mettre à jour'}
    updates['updated_at'] = datetime.now().isoformat(timespec='seconds')
    cols = ", ".join(f"{k} = ?" for k in updates)
    with get_conn() as conn:
        cur = conn.execute(f"UPDATE listes SET {cols} WHERE id = ?", (*updates.values(), liste_id))
        conn.commit()
        if cur.rowcount == 0:
            return {'success': False, 'error': 'Liste introuvable'}
    return {'success': True, 'liste': get_liste(liste_id)}


def archive_liste(liste_id: int, archived: bool = True) -> dict:
    return update_liste(liste_id, statut='archive' if archived else 'actif')


def delete_liste(liste_id: int) -> dict:
    """Supprime la liste ; ses prospects cascadent (FK), jamais des campagnes."""
    with get_conn() as conn:
        liste = conn.execute("SELECT nom FROM listes WHERE id = ?", (liste_id,)).fetchone()
        if not liste:
            return {'success': False, 'error': 'Liste introuvable'}
        conn.execute("DELETE FROM listes WHERE id = ?", (liste_id,))
        conn.commit()
    return {'success': True, 'nom': liste['nom']}


def _row_to_dict(row) -> dict | None:
    if row is None:
        return None
    return dict(row)


def get_or_create_corbeille(campagne_id: int) -> int:
    """Retourne l'id de la liste « 🗑 Corbeille » pour une campagne, la crée si absente."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM listes WHERE campagne_id = ? AND nom = '🗑 Corbeille' AND statut = 'actif'",
            (campagne_id,),
        ).fetchone()
        if row:
            return row['id']
        cur = conn.execute(
            """INSERT INTO listes (campagne_id, nom, description, icone, couleur, objectif, source, statut)
               VALUES (?, '🗑 Corbeille', 'Prospects retirés des listes', '🗑', '#8b5cf6', 'general', 'systeme', 'actif')""",
            (campagne_id,),
        )
        conn.commit()
        return cur.lastrowid


def unlink_prospects(liste_id: int, lead_ids: list[int]) -> dict:
    """Retire des prospects d'une liste en les déplaçant vers la Corbeille (non destructif)."""
    if not lead_ids:
        return {'success': False, 'error': 'Aucun lead sélectionné'}
    with get_conn() as conn:
        liste = conn.execute("SELECT campagne_id FROM listes WHERE id = ?", (liste_id,)).fetchone()
        if not liste:
            return {'success': False, 'error': 'Liste introuvable'}
        corbeille_id = get_or_create_corbeille(liste['campagne_id'])
        placeholders = ','.join('?' * len(lead_ids))
        cur = conn.execute(
            f"UPDATE prospects SET liste_id = ? WHERE liste_id = ? AND id IN ({placeholders})",
            (corbeille_id, liste_id, *lead_ids),
        )
        conn.commit()
        return {'success': True, 'moved': cur.rowcount}