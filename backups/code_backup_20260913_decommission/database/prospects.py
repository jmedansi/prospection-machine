# -*- coding: utf-8 -*-
"""
database/prospects.py — Repo v2 des prospects, rattachés à un objectif.

Ingestion : EXACTEMENT un schéma en sortie (adaptateur), quel que soit la source
(csv, json, scraping, IA). Aucune logique de séquencement/d'envoi ici — un prospect
ne fait que s'insérer, sa machine à états vit dans core/state_machine.py.
"""
import json
from datetime import datetime
from email.utils import parseaddr

from database.connection import get_conn, logger

PROSPECT_FIELDS = {
    'nom', 'prenom', 'email', 'telephone', 'entreprise', 'site_web',
    'adresse', 'ville', 'secteur', 'rating', 'nb_avis', 'source', 'score',
    'data_extra',
}


def _normalize_email(email):
    if not email:
        return ''
    email = (email or '').strip().lower()
    # retire les balises de type "Nom <toto@x.fr>" si présentes
    real = parseaddr(email)[1] or email
    return real.strip().lower()


def _is_in_suppression_list(conn, email: str) -> bool:
    if not email:
        return False
    row = conn.execute(
        "SELECT id FROM suppression_list WHERE LOWER(email) = ?", (email.lower(),)
    ).fetchone()
    return row is not None


def insert_prospect(objectif_id: int, *, source: str = 'import', data_extra=None, **fields) -> dict:
    """Insère un prospect dans un objectif.

    Règles :
      - `objectif_id` obligatoire (l'utilisateur choisit l'objectif AVANT tout lead).
      - doublon = même email déjà présent DANS le même objectif.
      - email présent dans suppression_list (globale) -> prospect refusé.
    Retourne {'success', 'prospect_id', 'statut_dedupe'} avec statut_dedupe dans
    {'created', 'doublon', 'suppression_list'}.
    """
    objectif_id = int(objectif_id)
    email = _normalize_email(fields.get('email'))
    nom = (fields.get('nom') or '').strip()
    if not email and not nom:
        return {'success': False, 'error': 'Lead sans nom ni email', 'statut_dedupe': None}

    with get_conn() as conn:
        if _is_in_suppression_list(conn, email):
            return {'success': False, 'error': 'Email dans la liste de suppression', 'statut_dedupe': 'suppression_list'}

        if email:
            existing = conn.execute(
                "SELECT id FROM prospects WHERE objectif_id = ? AND email = ?",
                (objectif_id, email),
            ).fetchone()
            if existing:
                return {'success': False, 'error': 'Doublon dans l\'objectif', 'statut_dedupe': 'doublon'}

        data_extra_json = json.dumps(data_extra, ensure_ascii=False) if data_extra else None
        now = datetime.now().isoformat(timespec='seconds')
        cur = conn.execute(
            """INSERT INTO prospects
               (objectif_id, source, nom, prenom, email, telephone, entreprise, site_web,
                adresse, ville, secteur, rating, nb_avis, score, data_extra,
                statut, statut_meta, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'qualifie', ?, ?, ?)""",
            (
                objectif_id, source or 'import',
                fields.get('nom'), fields.get('prenom'), email,
                fields.get('telephone'), fields.get('entreprise'), fields.get('site_web'),
                fields.get('adresse'), fields.get('ville'), fields.get('secteur'),
                fields.get('rating'), int(fields.get('nb_avis') or 0), fields.get('score'),
                data_extra_json,
                json.dumps({'created_at': now, 'source': source or 'import'}, ensure_ascii=False),
                now, now,
            ),
        )
        conn.execute(
            "INSERT INTO prospect_events (prospect_id, objectif_id, event_type, payload) VALUES (?, ?, 'creation', ?)",
            (cur.lastrowid, objectif_id, json.dumps({'source': source or 'import'}, ensure_ascii=False)),
        )
        conn.commit()
    logger.info("Prospect créé #%s dans objectif #%s", cur.lastrowid, objectif_id)
    return {'success': True, 'prospect_id': cur.lastrowid, 'statut_dedupe': 'created'}


def bulk_import(objectif_id: int, rows: list, source: str = 'import') -> dict:
    """Importe une liste de dicts (adaptateur déjà appliqué) dans un objectif.

    Retourne {'importes', 'doublons', 'supprimes', 'errors'}.
    """
    objectif_id = int(objectif_id)
    stats = {'importes': 0, 'doublons': 0, 'supprimes': 0, 'errors': 0, 'liste': []}
    if not isinstance(rows, list):
        return {**stats, 'errors': 0}

    with get_conn() as conn:
        suppression_emails = {
            r['email'].lower()
            for r in conn.execute("SELECT email FROM suppression_list").fetchall()
            if r['email']
        }
        existing_emails = {
            r['email'].lower()
            for r in conn.execute(
                "SELECT email FROM prospects WHERE objectif_id = ? AND email IS NOT NULL AND email != ''",
                (objectif_id,),
            ).fetchall()
            if r['email']
        }

    now = datetime.now().isoformat(timespec='seconds')
    base_meta = json.dumps({'created_at': now, 'source': source}, ensure_ascii=False)

    with get_conn() as conn:
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                stats['errors'] += 1
                continue
            email = _normalize_email(row.get('email'))
            nom = (row.get('nom') or '').strip()
            if not email and not nom:
                stats['errors'] += 1
                continue
            if email and email in suppression_emails:
                stats['supprimes'] += 1
                stats['liste'].append({'nom': nom, 'email': email, 'rejet': 'suppression_list'})
                continue
            if email and email in existing_emails:
                stats['doublons'] += 1
                stats['liste'].append({'nom': nom, 'email': email, 'rejet': 'doublon'})
                continue

            data_extra_json = json.dumps(row.get('data_extra'), ensure_ascii=False) if row.get('data_extra') else None
            cur = conn.execute(
                """INSERT INTO prospects
                   (objectif_id, source, nom, prenom, email, telephone, entreprise, site_web,
                    adresse, ville, secteur, rating, nb_avis, score, data_extra,
                    statut, statut_meta, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'qualifie', ?, ?, ?)""",
                (
                    objectif_id, source or 'import',
                    row.get('nom'), row.get('prenom'), email,
                    row.get('telephone'), row.get('entreprise'), row.get('site_web'),
                    row.get('adresse'), row.get('ville'), row.get('secteur'),
                    row.get('rating'), int(row.get('nb_avis') or 0), row.get('score'),
                    data_extra_json,
                    base_meta, now, now,
                ),
            )
            conn.execute(
                "INSERT INTO prospect_events (prospect_id, objectif_id, event_type, payload) VALUES (?, ?, 'import', ?)",
                (cur.lastrowid, objectif_id, json.dumps({'source': source}, ensure_ascii=False)),
            )
            if email:
                existing_emails.add(email)
            stats['importes'] += 1
            stats['liste'].append({'nom': nom, 'email': email, 'prospect_id': cur.lastrowid})
        conn.commit()
    logger.info("Import dans objectif #%s : %s importés, %s doublons, %s supprimés, %s erreurs",
                objectif_id, stats['importes'], stats['doublons'], stats['supprimes'], stats['errors'])
    return stats


def list_prospects(objectif_id: int, page: int = 1, limit: int = 50,
                   search: str = '', statut: str = '', include_archives: bool = False) -> dict:
    """Liste paginée des prospects d'un objectif."""
    objectif_id = int(objectif_id)
    page = max(1, int(page))
    limit = min(200, max(1, int(limit)))
    clauses = ['p.objectif_id = ?']
    params = [objectif_id]
    if search:
        clause = "(p.nom LIKE ? OR p.email LIKE ? OR p.entreprise LIKE ? OR p.ville LIKE ? OR p.secteur LIKE ?)"
        like = f"%{search}%"
        clauses.append(clause)
        params += [like] * 5
    if statut:
        clauses.append("p.statut = ?")
        params.append(statut)

    where = " AND ".join(clauses)
    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) AS n FROM prospects p WHERE {where}", params).fetchone()['n']
        total_pages = max(1, -(-total // limit))
        offset = (page - 1) * limit
        rows = conn.execute(
            f"""SELECT p.*, o.nom AS objectif_nom
                FROM prospects p JOIN objectifs o ON o.id = p.objectif_id
                WHERE {where}
                ORDER BY p.created_at DESC LIMIT ? OFFSET ?""",
            params + [limit, offset],
        ).fetchall()
        leads = []
        for r in rows:
            d = dict(r)
            try:
                d['statut_meta'] = json.loads(d.get('statut_meta') or '{}')
            except Exception:
                d['statut_meta'] = {}
            try:
                d['data_extra'] = json.loads(d.get('data_extra') or 'null')
            except Exception:
                pass
            leads.append(d)
    return {'leads': leads, 'page': page, 'limit': limit, 'total': total, 'total_pages': total_pages}


def get_prospect(prospect_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT p.*, o.nom AS objectif_nom
               FROM prospects p JOIN objectifs o ON o.id = p.objectif_id WHERE p.id = ?""",
            (prospect_id,),
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d['statut_meta'] = json.loads(d.get('statut_meta') or '{}')
        except Exception:
            d['statut_meta'] = {}
        events = conn.execute(
            "SELECT * FROM prospect_events WHERE prospect_id = ? ORDER BY created_at DESC LIMIT 100",
            (prospect_id,),
        ).fetchall()
        d['events'] = []
        for ev in events:
            e = dict(ev)
            try:
                e['payload'] = json.loads(e['payload'] or '{}')
            except Exception:
                e['payload'] = {}
            d['events'].append(e)
        return d


def update_prospect(prospect_id: int, **fields) -> dict:
    updates = {k: v for k, v in fields.items() if k in PROSPECT_FIELDS}
    if 'email' in updates:
        updates['email'] = _normalize_email(updates['email'])
    if not updates:
        return {'success': False, 'error': 'Aucun champ valide'}
    updates['updated_at'] = datetime.now().isoformat(timespec='seconds')
    cols = ", ".join(f"{k} = ?" for k in updates)
    with get_conn() as conn:
        cur = conn.execute(f"UPDATE prospects SET {cols} WHERE id = ?", (*updates.values(), prospect_id))
        conn.commit()
        if cur.rowcount == 0:
            return {'success': False, 'error': 'Prospect introuvable'}
    return {'success': True}


def set_ecarte(prospect_id: int, ecarte: bool) -> dict:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE prospects SET ecarte = ?, updated_at = ? WHERE id = ?",
            (1 if ecarte else 0, datetime.now().isoformat(timespec='seconds'), prospect_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            return {'success': False, 'error': 'Prospect introuvable'}
    return {'success': True}


def set_ne_plus_contacter(prospect_id: int, ne_plus_contacter: bool, raison: str = 'desinscription') -> dict:
    """Opposition au contact : flag + inscription à la suppression_list GLOBALE + transition d'état.

    Spec §2 : la désinscription met le prospect en `ne_plus_contacter` (définitif,
    toutes campagnes futures), d'où l'appel à la machine à états.
    """
    from core.state_machine import transition_prospect
    with get_conn() as conn:
        row = conn.execute("SELECT objectif_id, email FROM prospects WHERE id = ?", (prospect_id,)).fetchone()
        if not row:
            return {'success': False, 'error': 'Prospect introuvable'}
        conn.execute(
            "UPDATE prospects SET ne_plus_contacter = ?, updated_at = ? WHERE id = ?",
            (1 if ne_plus_contacter else 0, datetime.now().isoformat(timespec='seconds'), prospect_id),
        )
        conn.execute(
            "INSERT INTO prospect_events (prospect_id, objectif_id, event_type, payload) VALUES (?, ?, 'desinscription', ?)",
            (prospect_id, row['objectif_id'], json.dumps({'raison': raison, 'en': ne_plus_contacter}, ensure_ascii=False)),
        )
        if ne_plus_contacter and row['email']:
            conn.execute(
                "INSERT OR IGNORE INTO suppression_list (email, raison, source_objectif_id) VALUES (?, ?, ?)",
                (row['email'].lower(), raison, row['objectif_id']),
            )
        if not ne_plus_contacter and row['email']:
            conn.execute("DELETE FROM suppression_list WHERE LOWER(email) = ?", (row['email'].lower(),))
        conn.commit()

    if ne_plus_contacter:
        transition_prospect(prospect_id, 'ne_plus_contacter', reason=raison)
    return {'success': True}


def delete_prospect(prospect_id: int) -> dict:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM prospects WHERE id = ?", (prospect_id,))
        conn.commit()
        if cur.rowcount == 0:
            return {'success': False, 'error': 'Prospect introuvable'}
    return {'success': True}