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
                statut: str | None = None, search: str | None = None,
                include_corbeille: bool = False) -> list:
    """Liste les listes (optionnellement d'une seule campagne) avec comptages.

    Les poubelles (`type='corbeille'`) sont EXCLUES par défaut : ce ne sont pas des
    listes d'envoi. Chaque liste normale expose sa propre poubelle via
    `corbeille_id` + `nb_corbeille`.
    """
    with get_conn() as conn:
        sql = """SELECT l.*, c.nom AS campagne_nom,
                        (SELECT COUNT(*) FROM prospects p WHERE p.liste_id = l.id) AS nb_leads,
                        (SELECT MAX(p.updated_at) FROM prospects p WHERE p.liste_id = l.id) AS derniere_touche,
                        (SELECT cb.id FROM listes cb
                          WHERE cb.corbeille_de = l.id AND cb.statut = 'actif'
                          ORDER BY cb.id LIMIT 1) AS corbeille_id,
                        (SELECT COUNT(*) FROM prospects p
                          WHERE p.liste_id IN (SELECT cb2.id FROM listes cb2
                                               WHERE cb2.corbeille_de = l.id)) AS nb_corbeille
                 FROM listes l
                 JOIN campagnes c ON c.id = l.campagne_id """
        where = []
        params = []
        if not include_corbeille:
            where.append("(l.type IS NULL OR l.type != 'corbeille')")
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


CORBEILLE_NOM = '🗑 Corbeille'


def get_or_create_corbeille(campagne_id: int) -> int:
    """Corbeille ORPHELINE d'une campagne (défaut, sans liste source connue).

    Les déchets rangés au quotidien vont dans la poubelle de LEUR liste
    (`get_or_create_corbeille_liste`) ; celle-ci sert aux cas où la liste source
    n'existe plus (héritage, liste supprimée).
    """
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, type FROM listes WHERE campagne_id = ? AND type = 'corbeille' "
            "AND (corbeille_de IS NULL OR corbeille_de = 0) AND statut = 'actif' "
            "ORDER BY id LIMIT 1",
            (campagne_id,),
        ).fetchone()
        if not row:
            row = conn.execute(
                "SELECT id, type FROM listes WHERE campagne_id = ? AND nom = ? "
                "AND (corbeille_de IS NULL OR corbeille_de = 0) AND statut = 'actif' "
                "ORDER BY id LIMIT 1",
                (campagne_id, CORBEILLE_NOM),
            ).fetchone()
        if row:
            if (row['type'] or 'normal') != 'corbeille':
                conn.execute("UPDATE listes SET type = 'corbeille' WHERE id = ?", (row['id'],))
                conn.commit()
            return row['id']
        cur = conn.execute(
            """INSERT INTO listes (campagne_id, nom, description, icone, couleur,
                                   objectif, source, statut, type)
               VALUES (?, ?, 'Prospects retirés des listes', '🗑', '#8b5cf6',
                       'general', 'systeme', 'actif', 'corbeille')""",
            (campagne_id, CORBEILLE_NOM),
        )
        conn.commit()
        return cur.lastrowid


def get_or_create_corbeille_liste(liste_id: int) -> int:
    """Poubelle propre à UNE liste (`type='corbeille'`, `corbeille_de = liste_id`).

    C'est la destination de tout prospect retiré de `liste_id` : chaque liste a sa
    propre poubelle, la corbeille de campagne n'est qu'une vue qui les agrège.
    """
    with get_conn() as conn:
        src = conn.execute(
            "SELECT campagne_id, nom FROM listes WHERE id = ?", (liste_id,)
        ).fetchone()
        if not src:
            raise ValueError("Liste introuvable")
        row = conn.execute(
            "SELECT id FROM listes WHERE corbeille_de = ? AND statut = 'actif' "
            "ORDER BY id LIMIT 1",
            (liste_id,),
        ).fetchone()
        if row:
            return row['id']
        cur = conn.execute(
            """INSERT INTO listes (campagne_id, nom, description, icone, couleur,
                                   objectif, source, statut, type, corbeille_de)
               VALUES (?, ?, ?, '🗑', '#8b5cf6', 'general', 'systeme',
                       'actif', 'corbeille', ?)""",
            (src['campagne_id'], f"🗑 Poubelle — {src['nom'] or 'liste'}",
             f"Prospects retirés de « {src['nom'] or 'liste'} »", int(liste_id)),
        )
        conn.commit()
        return cur.lastrowid


def corbeille_counts(campagne_id: int | None = None) -> dict:
    """Comptages des poubelles : `{campagne_id: {'total': n, 'listes': {src_id: n}}}`.

    Alimente le badge « Poubelle (n) » de chaque liste et l'entrée « 🗑 Corbeille »
    en bas de sidebar (vue campagne).
    """
    with get_conn() as conn:
        sql = ("""SELECT cb.campagne_id AS cid, cb.corbeille_de AS src, COUNT(p.id) AS n
                  FROM listes cb
                  LEFT JOIN prospects p ON p.liste_id = cb.id
                  WHERE cb.type = 'corbeille'""")
        params = []
        if campagne_id is not None:
            sql += " AND cb.campagne_id = ?"
            params.append(int(campagne_id))
        sql += " GROUP BY cb.id"
        out: dict[int, dict] = {}
        for r in conn.execute(sql, params).fetchall():
            cid = int(r['cid'])
            bucket = out.setdefault(cid, {'total': 0, 'listes': {}})
            bucket['total'] += int(r['n'] or 0)
            if r['src']:
                bucket['listes'][int(r['src'])] = int(r['n'] or 0)
        return out


def restore_prospects(corbeille_id: int, lead_ids: list[int],
                      target_liste_id: int | None = None) -> dict:
    """Retour arrière : remet des prospects de la poubelle dans une liste normale.

    Cible par défaut = la liste source (`corbeille_de`). Une poubelle héritée
    (orpheline, `corbeille_de IS NULL`) impose `target_liste_id` — on ne devine
    jamais la liste d'origine.
    """
    if not lead_ids:
        return {'success': False, 'error': 'Aucun lead sélectionné'}
    with get_conn() as conn:
        cb = conn.execute(
            "SELECT id, campagne_id, type, corbeille_de FROM listes WHERE id = ?",
            (int(corbeille_id),),
        ).fetchone()
        if not cb or cb['type'] != 'corbeille':
            return {'success': False, 'error': 'Ce n\'est pas une poubelle'}
        if target_liste_id:
            target = int(target_liste_id)
        elif cb['corbeille_de']:
            target = int(cb['corbeille_de'])
        else:
            return {'success': False, 'error': 'liste_cible_requise',
                    'message': 'Poubelle héritée : choisis la liste de destination'}
        if target == int(corbeille_id):
            return {'success': False, 'error': 'La liste cible est la poubelle elle-même'}
        dst = conn.execute(
            "SELECT campagne_id, type FROM listes WHERE id = ?", (target,)
        ).fetchone()
        if not dst:
            return {'success': False, 'error': 'Liste cible introuvable'}
        if dst['type'] == 'corbeille':
            return {'success': False, 'error': 'La liste cible est elle-même une poubelle'}
        if int(dst['campagne_id']) != int(cb['campagne_id']):
            return {'success': False, 'error': 'La liste cible est dans une autre campagne'}
        ph = ','.join('?' * len(lead_ids))
        cur = conn.execute(
            f"UPDATE prospects SET liste_id = ? WHERE liste_id = ? AND id IN ({ph})",
            (target, int(corbeille_id), *[int(x) for x in lead_ids]),
        )
        conn.commit()
        logger.info("Restauration %s prospect(s) : poubelle #%s → liste #%s",
                    cur.rowcount, corbeille_id, target)
        return {'success': True, 'moved': cur.rowcount, 'target_liste_id': target}


def unlink_prospects(liste_id: int, lead_ids: list[int]) -> dict:
    """Retire des prospects d'une liste en les déposant dans la POUBELLE de cette
    liste (non destructif, réversible uniquement par migration SQL)."""
    if not lead_ids:
        return {'success': False, 'error': 'Aucun lead sélectionné'}
    with get_conn() as conn:
        liste = conn.execute("SELECT campagne_id, type FROM listes WHERE id = ?", (liste_id,)).fetchone()
        if not liste:
            return {'success': False, 'error': 'Liste introuvable'}
        if liste['type'] == 'corbeille':
            # Déjà à la poubelle : pas de poubelle-de-poubelle, on les met à terre
            # dans la corbeille orpheline de la campagne.
            target_id = get_or_create_corbeille(liste['campagne_id'])
        else:
            target_id = get_or_create_corbeille_liste(liste_id)
        placeholders = ','.join('?' * len(lead_ids))
        cur = conn.execute(
            f"UPDATE prospects SET liste_id = ? WHERE liste_id = ? AND id IN ({placeholders})",
            (target_id, liste_id, *lead_ids),
        )
        conn.commit()
        return {'success': True, 'moved': cur.rowcount, 'corbeille_id': target_id}