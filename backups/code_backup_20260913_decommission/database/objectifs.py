# -*- coding: utf-8 -*-
"""
database/objectifs.py — Repo v2 des objectifs de prospection.

Un objectif est le conteneur central défini par l'utilisateur avant tout lead
(ex. « Refonte site web », « Application scolaire »). Chaque prospect appartient
à un et un seul objectif.
"""
import json
from datetime import datetime

from database.connection import get_conn, logger

ALLOWED_FIELDS = {
    'description', 'statut', 'segment', 'sequence_id', 'template_id',
    'validation_telegram', 'backend_pref', 'max_touches', 'qualification',
    'envoi_auto',
}


def get_auto_send_enabled() -> bool:
    """Kill-switch global de l'auto-send v2 (`planning_settings.v2_auto_send`)."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM planning_settings WHERE key = 'v2_auto_send'"
        ).fetchone()
    return (row['value'] if row else '1') != '0'


def set_auto_send_enabled(enabled: bool) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO planning_settings (key, value) VALUES ('v2_auto_send', ?)",
            ('1' if enabled else '0'),
        )
        conn.commit()


def create_objectif(nom: str, **kwargs) -> dict:
    """Crée un objectif. `nom` est requis et unique."""
    nom = (nom or '').strip()
    if not nom:
        return {'success': False, 'error': 'Le nom de l\'objectif est obligatoire'}
    try:
        with get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO objectifs (nom, description, segment, validation_telegram,
                                          backend_pref, max_touches, qualification, envoi_auto)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    nom,
                    str(kwargs.get('description') or ''),
                    str(kwargs.get('segment') or ''),
                    1 if kwargs.get('validation_telegram') else 0,
                    kwargs.get('backend_pref') or 'auto',
                    int(kwargs.get('max_touches') or 3),
                    kwargs.get('qualification') or '',
                    1 if kwargs.get('envoi_auto', True) else 0,
                ),
            )
            conn.commit()
            objectif_id = cur.lastrowid
        logger.info("Objectif créé : #%s « %s »", objectif_id, nom)
        return {'success': True, 'objectif': get_objectif(objectif_id)}
    except Exception as e:
        logger.error("Erreur création objectif « %s » : %s", nom, e)
        msg = str(e)
        if 'UNIQUE' in msg:
            msg = f'Un objectif « {nom} » existe déjà'
        return {'success': False, 'error': msg}


def get_objectif(objectif_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM objectifs WHERE id = ?", (objectif_id,)).fetchone()
        return _row_to_dict(row)


def get_objectif_by_nom(nom: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM objectifs WHERE nom = ?", (nom,)).fetchone()
        return _row_to_dict(row)


def list_objectifs(include_archives: bool = False) -> list:
    """Liste les objectifs avec comptages (prospects total + par statut)."""
    with get_conn() as conn:
        sql = """SELECT o.*,
                        (SELECT COUNT(*) FROM prospects p WHERE p.objectif_id = o.id) AS nb_leads
                 FROM objectifs o """
        if not include_archives:
            sql += "WHERE o.statut = 'actif' "
        sql += "ORDER BY o.nom ASC"
        rows = conn.execute(sql).fetchall()
        result = []
        for r in rows:
            d = _row_to_dict(r)
            d['nb_leads'] = r['nb_leads']
            d['statut_breakdown'] = _statut_breakdown(conn, r['id'])
            result.append(d)
        return result


def _statut_breakdown(conn, objectif_id: int) -> dict:
    rows = conn.execute(
        "SELECT statut, COUNT(*) AS n FROM prospects WHERE objectif_id = ? GROUP BY statut",
        (objectif_id,),
    ).fetchall()
    return {r['statut']: r['n'] for r in rows}


def update_objectif(objectif_id: int, **kwargs) -> dict:
    updates = {k: v for k, v in kwargs.items() if k in ALLOWED_FIELDS}
    if not updates:
        return {'success': False, 'error': 'Aucun champ valide à mettre à jour'}
    updates['updated_at'] = datetime.now().isoformat(timespec='seconds')
    cols = ", ".join(f"{k} = ?" for k in updates)
    with get_conn() as conn:
        conn.execute(f"UPDATE objectifs SET {cols} WHERE id = ?", (*updates.values(), objectif_id))
        conn.commit()
    return {'success': True, 'objectif': get_objectif(objectif_id)}


def delete_objectif(objectif_id: int) -> dict:
    with get_conn() as conn:
        obj = conn.execute("SELECT nom FROM objectifs WHERE id = ?", (objectif_id,)).fetchone()
        if not obj:
            return {'success': False, 'error': 'Objectif introuvable'}
        conn.execute("DELETE FROM objectifs WHERE id = ?", (objectif_id,))
        conn.commit()
    return {'success': True, 'nom': obj['nom']}


def _row_to_dict(row) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    if d.get('qualification'):
        try:
            d['qualification'] = json.loads(d['qualification'])
        except Exception:
            pass
    return d