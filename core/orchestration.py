# -*- coding: utf-8 -*-
"""
core/orchestration.py — Orchestration des envois v2 (déclenchement manuel + relances).

Règles (2026-09, produit) :
  - L'envoi INITIAL est manuel SANS exception : `run_auto_send` refuse `manual=False`
    (`initial_manuel_obligatoire`). Le job scheduler `v2_send_initial` a été supprimé.
  - Les RELANCES sont automatiques mais TOUTE relance exige une validation Telegram
    (structurelle dans `sequence_engine.send_relance`) : l'auto-envoi passe uniquement
    par le batch validator (`ensure_batch_requests` → ✅ par liste → `consume_approvals`
    → `run_relances(..., approval='auto')`).
  - Par campagne `campagnes.envoi_auto` (0 = la campagne est gérée à la main,
    le scheduler ne la touche pas ; 1 = relances auto via batch validator).
  - Chaque émission passe par `sequence_engine` (verrous machine à états, template,
    humanisation, validation Telegram, quota). Le scheduler ne fait PAS de transition
    directe : tout passe par le tunnel.
"""
import os
import random
import time

from database.connection import get_conn, logger
from database import campagnes as campagnes_repo
from envoi import sequence_engine

DEFAULT_LIMIT_PER_CAMPAGNE = 10
DEFAULT_LIMIT_PER_OBJECTIF = DEFAULT_LIMIT_PER_CAMPAGNE  # compat

# ── Étalement « comportement humain » ───────────────────────────────────────
# Pause aléatoire entre DEUX envois consécutifs (jamais avant le premier ni après
# le dernier). Bornes configurables via PROSPECTION_DELAY_MIN / _MAX (secondes).
def _human_delay_range() -> tuple[int, int]:
    try:
        lo = int(os.getenv('PROSPECTION_DELAY_MIN', '30'))
    except ValueError:
        lo = 30
    try:
        hi = int(os.getenv('PROSPECTION_DELAY_MAX', '120'))
    except ValueError:
        hi = 120
    lo = max(0, min(lo, hi))
    return lo, max(lo, hi)


def _pause_humain(remaining: int, delay_range: tuple[int, int] | None = None,
                  cancel_event=None):
    """Pause aléatoire entre deux envois : ne joue que s'il reste des envois.
    
    `cancel_event` (threading.Event) : si fourni, la pause est interrompue
    immédiatement quand l'event est activé (annulation de l'envoi).
    """
    if remaining <= 1:
        return
    if delay_range is not None:
        lo, hi = delay_range
    else:
        lo, hi = _human_delay_range()
    if hi <= 0:
        return
    duration = random.uniform(lo, hi)
    if cancel_event is not None:
        cancel_event.wait(timeout=duration)  # reveil immédiat si annulation
    else:
        time.sleep(duration)


def candidates_for(campagne_id: int | None = None, limit: int | None = None, *,
                   objectif_id: int | None = None, liste_id: int | None = None,
                   prospect_ids: list[int] | None = None) -> list[dict]:
    """Prospects éligibles à l'initial d'une campagne (ou d'UNE liste).

    `qualifie`, non écarté, non opposé, email présent et absent de `suppression_list`.
    `liste_id` : restreint aux prospects de cette liste précise (bouton « Envoyer »
    d'une liste) — sinon toute la campagne.
    `prospect_ids` : restreint à une sélection précise de prospects (cases cochées) ;
    si vide ou None → aucun filtre (tous les éligibles).
    `limit=None` (ou ≤ 0) : AUCUNE limite — tous les éligibles sont renvoyés.
    Ordre FIFO (created_at ASC). Jamais de doublon : un statut != qualifie sort du lot.
    """
    if campagne_id is None:
        campagne_id = objectif_id
    sql = """SELECT p.id, p.nom, p.prenom, p.email
             FROM prospects p
             JOIN listes l ON p.liste_id = l.id
             WHERE l.campagne_id = ?
               AND p.statut = 'qualifie'
               AND p.ecarte = 0
               AND p.ne_plus_contacter = 0
               AND p.email IS NOT NULL AND p.email != ''
               AND lower(p.email) NOT IN (SELECT lower(email) FROM suppression_list)
          """
    params: list = [campagne_id]
    if liste_id is not None:
        sql += " AND l.id = ?"
        params.append(int(liste_id))
    if prospect_ids:
        placeholders = ",".join("?" * len(prospect_ids))
        sql += f" AND p.id IN ({placeholders})"
        params.extend(int(pid) for pid in prospect_ids)
    sql += " ORDER BY p.created_at ASC, p.id ASC"
    if limit is not None and int(limit) > 0:
        sql += " LIMIT ?"
        params.append(int(limit))
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
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
                  limit_per_objectif: int | None = None,
                  liste_id: int | None = None,
                  progress_callback = None,
                  delay_range: tuple[int, int] | None = None,
                  cancel_event = None,
                  prospect_ids: list[int] | None = None) -> dict:
    """Process un lot d'envois initiaux.

    - `manual=True` : bypass kill-switch global ET `envoi_auto` (action explicite de
      l'utilisateur, ex. bouton « Envoyer maintenant » d'une campagne en manuel).
    - `liste_id` : restreint l'envoi aux prospects d'UNE liste précise (bouton
      « Envoyer » de la liste dans l'onglet Listes).
    - RÈGLE PRODUIT : l'envoi initial est MANUEL SANS EXCEPTION. `manual=False`
      est refusé dès l'entrée (les jobs d'auto-send d'initial ont été retirés du
      scheduler) — aucune émission automatique possible, même si le kill-switch
      ou `envoi_auto` est à 1.
    - Rythme humain : une pause aléatoire est respectée entre DEUX envois
      consécutifs (jamais avant le 1er ni après le dernier).
    - `progress_callback` : optionnel `callable(current, total, lead_dict, result_dict)` pour le suivi temps réel.
    """
    if not manual:
        return {'success': True, 'runs': [], 'quoted': 'initial_manuel_obligatoire',
                'message': 'Les envois initiaux passent par le bouton manuel uniquement'}
    target, err = _targets(campagne_id, objectif_id, manual)
    if err is not None:
        return err
    # `None` (non fourni) ou ≤ 0 = AUCUNE limite : le bouton « Envoyer » envoie
    # tout ce qui est éligible dans la liste / la campagne ciblée.
    limit = None
    if limit_per_campagne is not None and int(limit_per_campagne) > 0:
        limit = int(limit_per_campagne)
    elif limit_per_objectif is not None and int(limit_per_objectif) > 0:
        limit = int(limit_per_objectif)

    runs = []
    total_candidates = sum(len(candidates_for(obj['id'], limit, liste_id=liste_id, prospect_ids=prospect_ids)) for obj in target)
    global_current = 0

    for obj in target:
        ids = candidates_for(obj['id'], limit, liste_id=liste_id, prospect_ids=prospect_ids)
        stats = {'campagne': obj['id'], 'nom': obj['nom'], 'candidats': len(ids), 'details': []}
        for i, cand in enumerate(ids):
            if i > 0:
                _pause_humain(len(ids) - i, delay_range=delay_range, cancel_event=cancel_event)
            if cancel_event is not None and cancel_event.is_set():
                break
            res = sequence_engine.send_initial(obj['id'], cand['id'])
            stats['details'].append({'prospect_id': cand['id'], 'nom': cand.get('nom'), 'email': cand.get('email'),
                                     'statut': res.get('statut'), 'message': res.get('message')})
            global_current += 1
            if callable(progress_callback):
                try:
                    progress_callback(global_current, total_candidates, cand, res)
                except Exception as e:
                    logger.error("[orchestration] progress_callback error: %s", e)
            logger.info("[orchestration] campagne %s prospect %s → %s (%s/%s)",
                        obj['id'], cand['id'], res.get('statut'), global_current, total_candidates)
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
                 objectif_id: int | None = None, liste_id: int | None = None,
                 prospect_ids: list[int] | None = None) -> list[dict]:
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
    if prospect_ids:
        ids_ph = ",".join("?" * len(prospect_ids))
        sql_where += f" AND p.id IN ({ids_ph})"
        params.extend(int(pid) for pid in prospect_ids)
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
                 approval: str | None = None,
                 progress_callback = None,
                 delay_range: tuple[int, int] | None = None,
                 cancel_event = None,
                 prospect_ids: list[int] | None = None) -> dict:
    """Process un lot de relances dues (mêmes règles que l'auto-send initial).

    - `campagne_id=None` (mode scheduler) : kill-switch global + `enabled_campagnes()`.
    - `manual=True` : bypass kill-switch ET `envoi_auto`.
    - `liste_id` : restreint aux prospects d'une liste précise (lot validé Telegram).
    - `approval` : traite toutes les candidatures comme validées (`'auto'` après ✅ lot)
      — sinon rôle conservé du paramètre passé à `send_relance`.
    - `progress_callback` : optionnel `callable(current, total, lead_dict, result_dict)` pour le suivi temps réel.
    Chaque relance passe par `sequence_engine.send_relance(...)` (verrous + template
    position N + humain + validation Telegram + max_touches).
    """
    target, err = _targets(campagne_id, objectif_id, manual)
    if err is not None:
        return err

    # `None` ou ≤ 0 = AUCUNE limite (bouton « Envoyer ») ; sinon borné.
    if limit_per_campagne is not None and int(limit_per_campagne) > 0:
        limit = int(limit_per_campagne)
    else:
        limit = None
    runs = []
    
    total_candidates = 0
    all_cands_by_obj = []
    for obj in target:
        due = relances_due(obj['id'], liste_id=liste_id, prospect_ids=prospect_ids)
        cands = due if limit is None else due[:limit]
        total_candidates += len(cands)
        all_cands_by_obj.append((obj, cands))

    global_current = 0
    for obj, cands in all_cands_by_obj:
        stats = {'campagne': obj['id'], 'nom': obj['nom'], 'candidats': len(cands), 'details': []}
        for i, cand in enumerate(cands):
            if i > 0:
                _pause_humain(len(cands) - i, delay_range=delay_range, cancel_event=cancel_event)
            if cancel_event is not None and cancel_event.is_set():
                break
            res = sequence_engine.send_relance(obj['id'], cand['id'], approval=approval)
            stats['details'].append({'prospect_id': cand['id'], 'statut': res.get('statut'),
                                     'message': res.get('message')})
            global_current += 1
            if callable(progress_callback):
                try:
                    progress_callback(global_current, total_candidates, cand, res)
                except Exception as e:
                    logger.error("[orchestration] relance progress_callback error: %s", e)
            logger.info("[orchestration] relance campagne %s prospect %s → %s (%s/%s)",
                        obj['id'], cand['id'], res.get('statut'), global_current, total_candidates)
        runs.append(stats)
    return {'success': True, 'runs': runs, 'total': sum(len(r['details']) for r in runs)}