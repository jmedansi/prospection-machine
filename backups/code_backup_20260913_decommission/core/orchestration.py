# -*- coding: utf-8 -*-
"""
core/orchestration.py — Orchestration des envois v2 (scheduler + déclenchement manuel).

Règles :
  - Kill-switch global `planning_settings.v2_auto_send` ('1' par défaut) : coupé →
    l'auto-send ne tourne pas (le déclenchement manuel reste possible).
  - Par objectif `objectifs.envoi_auto` (0 = l'objectif est géré à la main,
    le scheduler ne le touche pas ; 1 = il participe à l'auto-send).
  - Chaque émission passe par `sequence_engine.send_initial(...)` : verrous machine à
    états, template position 0, humanisation, validation Telegram si configurée, quota.
    Le job scheduler ne fait PAS de transition directe : tout passe par le tunnel.
"""
from database.connection import get_conn, logger
from database import objectifs as objectifs_repo
from envoi import sequence_engine

DEFAULT_LIMIT_PER_OBJECTIF = 10


def candidates_for(objectif_id: int, limit: int = DEFAULT_LIMIT_PER_OBJECTIF) -> list[dict]:
    """Prospects éligibles à l'initial d'un objectif.

    `qualifie`, non écarté, non opposé, email présent et absent de `suppression_list`.
    Ordre FIFO (created_at ASC). Jamais de doublon : un statut != qualifie sort du lot.
    """
    limit = max(1, int(limit or DEFAULT_LIMIT_PER_OBJECTIF))
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT id, nom, prenom, email
               FROM prospects
               WHERE objectif_id = ?
                 AND statut = 'qualifie'
                 AND ecarte = 0
                 AND ne_plus_contacter = 0
                 AND email IS NOT NULL AND email != ''
                 AND lower(email) NOT IN (SELECT lower(email) FROM suppression_list)
               ORDER BY created_at ASC, id ASC
               LIMIT ?""",
            (objectif_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def enabled_objectifs() -> list[dict]:
    """Objectifs actifs prévus pour l'auto-send (`statut='actif'` ET `envoi_auto=1`)."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, nom, envoi_auto FROM objectifs WHERE statut = 'actif' AND envoi_auto = 1 ORDER BY nom ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def run_auto_send(objectif_id: int | None = None,
                  limit_per_objectif: int = DEFAULT_LIMIT_PER_OBJECTIF,
                  manual: bool = False) -> dict:
    """Process un lot d'envois initiaux.

    - `objectif_id=None` (mode scheduler) : respecte le kill-switch global et la liste
      `enabled_objectifs()`.
    - `manual=True` : bypass kill-switch global ET `envoi_auto` (action explicite de
      l'utilisateur, ex. bouton « Envoyer maintenant » d'un objectif en manuel).
    """
    if objectif_id is not None:
        target = [objectifs_repo.get_objectif(objectif_id)]
        if not target[0]:
            return {'success': False, 'error': 'Objectif introuvable'}
        if not (manual or target[0].get('envoi_auto')):
            return {'success': True, 'runs': [], 'quoted': 'auto_off', 'message': 'Auto-envoi coupé pour cet objectif'}
    else:
        if not (manual or objectifs_repo.get_auto_send_enabled()):
            return {'success': True, 'runs': [], 'quoted': 'global_off', 'message': 'Auto-envoi global coupé'}
        target = enabled_objectifs()
        if not target:
            return {'success': True, 'runs': [], 'quoted': 'no_target', 'message': 'Aucun objectif en auto-envoi'}

    runs = []
    for obj in target:
        ids = candidates_for(obj['id'], limit_per_objectif)
        stats = {'objectif': obj['id'], 'nom': obj['nom'], 'candidats': len(ids), 'details': []}
        for cand in ids:
            res = sequence_engine.send_initial(obj['id'], cand['id'])
            stats['details'].append({'prospect_id': cand['id'], 'statut': res.get('statut'), 'message': res.get('message')})
            logger.info("[orchestration] obj %s prospect %s → %s", obj['id'], cand['id'], res.get('statut'))
        runs.append(stats)
    return {'success': True, 'runs': runs, 'total': sum(len(r['details']) for r in runs)}


# ─── Relances (positions > 0) ─────────────────────────────────────────────────

def relances_due(objectif_id: int, now=None) -> list[dict]:
    """Prospects éligibles à la relance suivante.

    Statut ∈ {en_sequence, relance_1, relance_2}, dernière touche (initial/relance)
    + `delai_jours` du template suivant ≤ maintenant, template suivant actif.
    """
    from datetime import datetime, timedelta
    from envoi import template_registry
    from envoi import sequence_engine

    now = now or datetime.utcnow()
    statuts = tuple(sequence_engine.STATUT_NEXT_POSITION.keys())
    placeholders = ",".join("?" * len(statuts))
    with get_conn() as conn:
        rows = conn.execute(
            f"""SELECT p.id, p.statut,
                       MAX(CASE WHEN ev.event_type IN ('initial','relance_1','relance_2','relance_3')
                                THEN ev.created_at END) AS last_touch_at
                FROM prospects p
                LEFT JOIN prospect_events ev ON ev.prospect_id = p.id
                WHERE p.objectif_id = ? AND p.statut IN ({placeholders})
                  AND p.ecarte = 0 AND p.ne_plus_contacter = 0
                GROUP BY p.id""",
            (objectif_id, *statuts),
        ).fetchall()

    due = []
    for r in rows:
        position = sequence_engine.STATUT_NEXT_POSITION[r['statut']]
        template = template_registry.get_step(objectif_id, position=position)
        if not template:
            continue
        last = r['last_touch_at']
        if not last:
            continue
        try:
            last_dt = datetime.strptime(str(last)[:19], '%Y-%m-%d %H:%M:%S')
        except ValueError:
            continue
        if last_dt + timedelta(days=int(template.get('delai_jours') or 0)) <= now:
            due.append({'id': r['id'], 'statut': r['statut'], 'last_touch_at': last,
                        'position': position})
    return due


def run_relances(objectif_id: int | None = None,
                 limit_per_objectif: int = 20,
                 manual: bool = False) -> dict:
    """Process un lot de relances dues (mêmes règles que l'auto-send initial).

    - `objectif_id=None` (mode scheduler) : kill-switch global + `enabled_objectifs()`.
    - `manual=True` : bypass kill-switch ET `envoi_auto`.
    Chaque relance passe par `sequence_engine.send_relance(...)` (verrous + template
    position N + humain + validation Telegram + max_touches).
    """
    if objectif_id is not None:
        target = [objectifs_repo.get_objectif(objectif_id)]
        if not target[0]:
            return {'success': False, 'error': 'Objectif introuvable'}
        if not (manual or target[0].get('envoi_auto')):
            return {'success': True, 'runs': [], 'quoted': 'auto_off', 'message': 'Auto-envoi coupé pour cet objectif'}
    else:
        if not (manual or objectifs_repo.get_auto_send_enabled()):
            return {'success': True, 'runs': [], 'quoted': 'global_off', 'message': 'Auto-envoi global coupé'}
        target = enabled_objectifs()
        if not target:
            return {'success': True, 'runs': [], 'quoted': 'no_target', 'message': 'Aucun objectif en auto-envoi'}

    limit = max(1, int(limit_per_objectif))
    runs = []
    for obj in target:
        cands = relances_due(obj['id'])[:limit]
        stats = {'objectif': obj['id'], 'nom': obj['nom'], 'candidats': len(cands), 'details': []}
        for cand in cands:
            res = sequence_engine.send_relance(obj['id'], cand['id'])
            stats['details'].append({'prospect_id': cand['id'], 'statut': res.get('statut'),
                                     'message': res.get('message')})
            logger.info("[orchestration] relance obj %s prospect %s → %s",
                        obj['id'], cand['id'], res.get('statut'))
        runs.append(stats)
    return {'success': True, 'runs': runs, 'total': sum(len(r['details']) for r in runs)}