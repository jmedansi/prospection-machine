# -*- coding: utf-8 -*-
"""
core/orchestration.py — Orchestration des envois v2 (scheduler + déclenchement manuel).

Règles :
  - Kill-switch global `planning_settings.v2_auto_send` ('1' par défaut) : coupé →
    l'auto-send ne tourne pas (le déclenchement manuel reste possible).
  - Par campagne `campagnes.envoi_auto` (0 = la campagne est gérée à la main,
    le scheduler ne la touche pas ; 1 = elle participe à l'auto-send).
  - Chaque émission passe par `sequence_engine.send_initial(...)` : verrous machine à
    états, template position 0, humanisation, validation Telegram si configurée, quota.
    Le job scheduler ne fait PAS de transition directe : tout passe par le tunnel.
"""
from database.connection import get_conn, logger
from database import campagnes as campagnes_repo
from envoi import sequence_engine

DEFAULT_LIMIT_PER_CAMPAGNE = 10
DEFAULT_LIMIT_PER_OBJECTIF = DEFAULT_LIMIT_PER_CAMPAGNE  # compat


def candidates_for(campagne_id: int | None = None, limit: int | None = None, *,
                   objectif_id: int | None = None) -> list[dict]:
    """Prospects éligibles à l'initial d'une campagne.

    `qualifie`, non écarté, non opposé, email présent et absent de `suppression_list`.
    Ordre FIFO (created_at ASC). Jamais de doublon : un statut != qualifie sort du lot.
    """
    if campagne_id is None:
        campagne_id = objectif_id
    limit = max(1, int(limit or DEFAULT_LIMIT_PER_CAMPAGNE))
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT p.id, p.nom, p.prenom, p.email
               FROM prospects p
               JOIN listes l ON p.liste_id = l.id
               WHERE l.campagne_id = ?
                 AND p.statut = 'qualifie'
                 AND p.ecarte = 0
                 AND p.ne_plus_contacter = 0
                 AND p.email IS NOT NULL AND p.email != ''
                 AND lower(p.email) NOT IN (SELECT lower(email) FROM suppression_list)
               ORDER BY p.created_at ASC, p.id ASC
               LIMIT ?""",
            (campagne_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def enabled_campagnes() -> list[dict]:
    """Campagnes actives prévues pour l'auto-send (`statut='actif'` ET `envoi_auto=1`)."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, nom, envoi_auto, validation_relances FROM campagnes WHERE statut = 'actif' AND envoi_auto = 1 ORDER BY nom ASC"
        ).fetchall()
    return [dict(r) for r in rows]


enabled_objectifs = enabled_campagnes  # compat


def _targets(campagne_id, objectif_id, manual):
    if campagne_id is None and objectif_id is not None:
        campagne_id = objectif_id
    if campagne_id is not None:
        target = [campagnes_repo.get_campagne(campagne_id)]
        if not target[0]:
            return None, {'success': False, 'error': 'Campagne introuvable'}
        if not (manual or target[0].get('envoi_auto')):
            return None, {'success': True, 'runs': [], 'quoted': 'auto_off',
                          'message': 'Auto-envoi coupé pour cette campagne'}
    else:
        if not (manual or campagnes_repo.get_auto_send_enabled()):
            return None, {'success': True, 'runs': [], 'quoted': 'global_off',
                          'message': 'Auto-envoi global coupé'}
        target = enabled_campagnes()
        if not target:
            return None, {'success': True, 'runs': [], 'quoted': 'no_target',
                          'message': 'Aucune campagne en auto-envoi'}
    return target, None


def run_auto_send(campagne_id: int | None = None,
                  limit_per_campagne: int | None = None,
                  manual: bool = False, *,
                  objectif_id: int | None = None,
                  limit_per_objectif: int | None = None) -> dict:
    """Process un lot d'envois initiaux.

    - `campagne_id=None` (mode scheduler) : respecte le kill-switch global et la liste
      `enabled_campagnes()`.
    - `manual=True` : bypass kill-switch global ET `envoi_auto` (action explicite de
      l'utilisateur, ex. bouton « Envoyer maintenant » d'une campagne en manuel).
    """
    target, err = _targets(campagne_id, objectif_id, manual)
    if err is not None:
        return err
    limit = max(1, int(limit_per_campagne or limit_per_objectif or DEFAULT_LIMIT_PER_CAMPAGNE))

    runs = []
    for obj in target:
        ids = candidates_for(obj['id'], limit)
        stats = {'campagne': obj['id'], 'nom': obj['nom'], 'candidats': len(ids), 'details': []}
        for cand in ids:
            res = sequence_engine.send_initial(obj['id'], cand['id'])
            stats['details'].append({'prospect_id': cand['id'], 'statut': res.get('statut'), 'message': res.get('message')})
            logger.info("[orchestration] campagne %s prospect %s → %s", obj['id'], cand['id'], res.get('statut'))
        runs.append(stats)
    return {'success': True, 'runs': runs, 'total': sum(len(r['details']) for r in runs)}


# ─── Relances (positions > 0) ─────────────────────────────────────────────────

def _next_business_day(dt):
    """Reporte `dt` au lundi suivant si elle tombe un samedi (5) / dimanche (6)."""
    from datetime import timedelta
    if dt.weekday() >= 5:
        return dt + timedelta(days=7 - dt.weekday())
    return dt


def is_business_day(dt) -> bool:
    return dt.weekday() < 5


def relances_due(campagne_id: int | None = None, now=None, *,
                 objectif_id: int | None = None, liste_id: int | None = None) -> list[dict]:
    """Prospects éligibles à la relance suivante.

    Statut ∈ {en_sequence, relance_1, relance_2}, dernière touche (initial/relance)
    + `delai_jours` du template suivant ≤ maintenant, template suivant actif.
    `liste_id` : restreint au lot d'une liste précise (confirmation par lot).

    Jours ouvrés uniquement : les samedis/dimanches sont EXCLUS des jours de relance.
    Une relance dont l'échéance (`dernière touche + delai_jours`) tombe un week-end est
    reportée au lundi suivant — et le week-end lui-même ne déclenche aucun envoi.
    """
    if campagne_id is None:
        campagne_id = objectif_id
    from datetime import datetime, timedelta
    from envoi import template_registry

    now = now or datetime.utcnow()
    statuts = tuple(sequence_engine.STATUT_NEXT_POSITION.keys())
    placeholders = ",".join("?" * len(statuts))
    params = [campagne_id, *statuts]
    sql_where = "l.campagne_id = ? AND p.statut IN ({placeholders})".format(placeholders=placeholders)
    if liste_id is not None:
        sql_where += " AND l.id = ?"
        params.append(int(liste_id))
    with get_conn() as conn:
        rows = conn.execute(
            f"""SELECT p.id, p.statut, l.id AS liste_id, l.nom AS liste_nom,
                       MAX(CASE WHEN ev.event_type IN ('initial','relance_1','relance_2','relance_3')
                                THEN ev.created_at END) AS last_touch_at
                FROM prospects p
                JOIN listes l ON p.liste_id = l.id
                LEFT JOIN prospect_events ev ON ev.prospect_id = p.id
                WHERE {sql_where}
                  AND p.ecarte = 0 AND p.ne_plus_contacter = 0
                GROUP BY p.id""",
            params,
        ).fetchall()

    due = []
    for r in rows:
        position = sequence_engine.STATUT_NEXT_POSITION[r['statut']]
        template = template_registry.get_step(campagne_id, position=position)
        if not template:
            continue
        last = r['last_touch_at']
        if not last:
            continue
        try:
            last_dt = datetime.strptime(str(last)[:19], '%Y-%m-%d %H:%M:%S')
        except ValueError:
            continue
        # ── Jours ouvrés : jamais de relance le samedi/dimanche ──
        if not is_business_day(now):
            continue
        scheduled = last_dt + timedelta(days=int(template.get('delai_jours') or 0))
        effective = _next_business_day(scheduled)
        if effective <= now:
            due.append({'id': r['id'], 'statut': r['statut'], 'last_touch_at': last,
                        'position': position, 'liste_id': r['liste_id'],
                        'liste_nom': r['liste_nom']})
    return due


def run_relances(campagne_id: int | None = None,
                 limit_per_campagne: int = 20,
                 manual: bool = False, *,
                 objectif_id: int | None = None,
                 liste_id: int | None = None,
                 approval: str | None = None) -> dict:
    """Process un lot de relances dues (mêmes règles que l'auto-send initial).

    - `campagne_id=None` (mode scheduler) : kill-switch global + `enabled_campagnes()`.
    - `manual=True` : bypass kill-switch ET `envoi_auto`.
    - `liste_id` : restreint aux prospects d'une liste précise (lot validé Telegram).
    - `approval` : traite toutes les candidatures comme validées (`'auto'` après ✅ lot)
      — sinon rôle conservé du paramètre passé à `send_relance`.
    Chaque relance passe par `sequence_engine.send_relance(...)` (verrous + template
    position N + humain + validation Telegram + max_touches).
    """
    target, err = _targets(campagne_id, objectif_id, manual)
    if err is not None:
        return err

    limit = max(1, int(limit_per_campagne))
    runs = []
    for obj in target:
        cands = relances_due(obj['id'], liste_id=liste_id)[:limit]
        stats = {'campagne': obj['id'], 'nom': obj['nom'], 'candidats': len(cands), 'details': []}
        for cand in cands:
            res = sequence_engine.send_relance(obj['id'], cand['id'], approval=approval)
            stats['details'].append({'prospect_id': cand['id'], 'statut': res.get('statut'),
                                     'message': res.get('message')})
            logger.info("[orchestration] relance campagne %s prospect %s → %s",
                        obj['id'], cand['id'], res.get('statut'))
        runs.append(stats)
    return {'success': True, 'runs': runs, 'total': sum(len(r['details']) for r in runs)}