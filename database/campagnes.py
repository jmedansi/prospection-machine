# -*- coding: utf-8 -*-
"""
database/campagnes.py — Repo v2 des campagnes de prospection.

Une campagne est le conteneur central (remplace « objectif ») défini par
l'utilisateur avant tout lead : elle porte la CONFIGURATION du cycle de vie
(max_touches, validation_telegram, envoi_auto, backend_pref…) partagée par ses
listes. Chaque carte (liste) appartient à une et une seule campagne.
"""
import json
from datetime import datetime

from database.connection import get_conn, logger
from database.listes import create_liste

ALLOWED_FIELDS = {
    'description', 'statut', 'segment', 'sequence_id', 'template_id',
    'validation_telegram', 'backend_pref', 'max_touches', 'qualification',
    'envoi_auto', 'validation_relances',
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


def create_campagne(nom: str, **kwargs) -> dict:
    """Crée une campagne (+ sa 1ère liste par défaut). `nom` est requis et unique."""
    nom = (nom or '').strip()
    if not nom:
        return {'success': False, 'error': 'Le nom de la campagne est obligatoire'}
    try:
        with get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO campagnes (nom, description, segment, validation_telegram,
                                          backend_pref, max_touches, qualification, envoi_auto,
                                          validation_relances)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    nom,
                    str(kwargs.get('description') or ''),
                    str(kwargs.get('segment') or ''),
                    1 if kwargs.get('validation_telegram') else 0,
                    kwargs.get('backend_pref') or 'auto',
                    int(kwargs.get('max_touches') or 3),
                    kwargs.get('qualification') or '',
                    1 if kwargs.get('envoi_auto', True) else 0,
                    1 if kwargs.get('validation_relances') else 0,
                ),
            )
            campagne_id = cur.lastrowid
        create_liste(campagne_id, nom, kwargs.get('description') or '')
        logger.info("Campagne créée : #%s « %s »", campagne_id, nom)
        return {'success': True, 'campagne': get_campagne(campagne_id)}
    except Exception as e:
        logger.error("Erreur création campagne « %s » : %s", nom, e)
        msg = str(e)
        if 'UNIQUE' in msg:
            msg = f'Une campagne « {nom} » existe déjà'
        return {'success': False, 'error': msg}


def get_campagne(campagne_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM campagnes WHERE id = ?", (campagne_id,)).fetchone()
        return _row_to_dict(row)


def get_campagne_by_nom(nom: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM campagnes WHERE nom = ?", (nom,)).fetchone()
        return _row_to_dict(row)


def list_campagnes(include_archives: bool = False) -> list:
    """Liste les campagnes avec comptages (nb_listes, prospects total + par statut)."""
    with get_conn() as conn:
        sql = """SELECT c.*,
                        (SELECT COUNT(*) FROM listes l
                          JOIN prospects p ON p.liste_id = l.id
                         WHERE l.campagne_id = c.id) AS nb_leads,
                        (SELECT COUNT(*) FROM listes l
                         WHERE l.campagne_id = c.id AND l.statut = 'actif') AS nb_listes
                 FROM campagnes c """
        if not include_archives:
            sql += "WHERE c.statut = 'actif' "
        sql += "ORDER BY c.nom ASC"
        rows = conn.execute(sql).fetchall()
        result = []
        for r in rows:
            d = _row_to_dict(r)
            d['nb_leads'] = r['nb_leads']
            d['nb_listes'] = r['nb_listes']
            d['statut_breakdown'] = _statut_breakdown(conn, r['id'])
            result.append(d)
        return result


def _statut_breakdown(conn, campagne_id: int) -> dict:
    rows = conn.execute(
        """SELECT p.statut, COUNT(*) AS n
           FROM prospects p JOIN listes l ON p.liste_id = l.id
           WHERE l.campagne_id = ? GROUP BY p.statut""",
        (campagne_id,),
    ).fetchall()
    return {r['statut']: r['n'] for r in rows}


def update_campagne(campagne_id: int, **kwargs) -> dict:
    updates = {k: v for k, v in kwargs.items() if k in ALLOWED_FIELDS}
    if not updates:
        return {'success': False, 'error': 'Aucun champ valide à mettre à jour'}
    updates['updated_at'] = datetime.now().isoformat(timespec='seconds')
    cols = ", ".join(f"{k} = ?" for k in updates)
    with get_conn() as conn:
        conn.execute(f"UPDATE campagnes SET {cols} WHERE id = ?", (*updates.values(), campagne_id))
        conn.commit()
    return {'success': True, 'campagne': get_campagne(campagne_id)}


def delete_campagne(campagne_id: int) -> dict:
    """Supprime la campagne ; les listes et prospects cascadent (FK)."""
    with get_conn() as conn:
        obj = conn.execute("SELECT nom FROM campagnes WHERE id = ?", (campagne_id,)).fetchone()
        if not obj:
            return {'success': False, 'error': 'Campagne introuvable'}
        conn.execute("DELETE FROM campagnes WHERE id = ?", (campagne_id,))
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