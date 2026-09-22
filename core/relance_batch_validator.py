# -*- coding: utf-8 -*-
"""
core/relance_batch_validator.py — Validation Telegram PAR LOT des relances v2.

Principe : pour une campagne avec `campagnes.validation_relances=1`, on ne demande pas
un ✅ par prospect mais UN message Telegram par liste (`callback_id` =
`v2_batch_{campagne_id}_{liste_id}`). Une réponse ✅ déclenche l'envoi de TOUTES les
relances dues de la liste via `orchestration.run_relances(..., liste_id=...,
approval='auto')` ; ❌ → aucune relance envoyée.

États persistés dans `relance_batches` (voir schema.migrate_v2_schema) :
    pending  → demande envoyée, en attente de réponse ✅/❌
    sent     → ✅ consommé, relances envoyées
    refuse   → ❌ : aucune relance envoyée ; pas de re-demande tant que la position
               ET le nombre de prospects à relancer restent inchangés.
"""
import logging

from database.connection import get_conn

logger = logging.getLogger(__name__)

_BATCH_HIGH_LIMIT = 500  # un lot validé lance TOUTE la liste (pas de plafond de 20)
_TIMEOUT_MINUTES = 2880  # 48h, cohérent avec la validation par prospect


def batch_callback(campagne_id: int, liste_id: int) -> str:
    return f"v2_batch_{int(campagne_id)}_{int(liste_id)}"


def _batch_state(conn, callback_id_value: str):
    row = conn.execute(
        "SELECT campagne_id, liste_id, position, count, statut FROM relance_batches "
        "WHERE callback_id = ?",
        (callback_id_value,),
    ).fetchone()
    return dict(row) if row else None


def _save_batch(conn, callback_id_value: str, campagne_id: int, liste_id: int,
                position: int, count: int, statut: str):
    conn.execute(
        """INSERT INTO relance_batches (callback_id, campagne_id, liste_id, position,
                                        count, statut, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
           ON CONFLICT(callback_id) DO UPDATE SET
               campagne_id = excluded.campagne_id,
               liste_id    = excluded.liste_id,
               position    = excluded.position,
               count       = excluded.count,
               statut      = excluded.statut,
               updated_at  = datetime('now')""",
        (callback_id_value, int(campagne_id), int(liste_id), int(position),
         int(count), statut),
    )


def ensure_batch_requests() -> dict:
    """Pour chaque campagne `validation_relances=1`, demande un ✅ par liste ayant des
    relances dues.

    Idempotent : ne renvoie jamais une demande déjà `pending` (réponse traitée par
    `consume_approvals`), et ne redemande pas un lot `refuse`/`sent` tant que sa
    position ET son count n'ont pas changé.
    """
    from core import orchestration
    try:
        from core.telegram_adapter import send_validation_request
    except Exception:
        send_validation_request = None

    campagnes = [c for c in orchestration.enabled_campagnes() if c.get('validation_relances')]
    requests = []
    for camp in campagnes:
        cid = camp['id']
        try:
            due = orchestration.relances_due(cid)[:_BATCH_HIGH_LIMIT]
        except Exception as e:
            logger.error("[relance_batch] relances_due campagne %s: %s", cid, e)
            continue
        grouped: dict[int, list[dict]] = {}
        for cand in due:
            grouped.setdefault(cand['liste_id'], []).append(cand)

        for lid, cands in grouped.items():
            cb = batch_callback(cid, lid)
            position = cands[0]['position']
            count = len(cands)
            nom = cands[0].get('liste_nom') or f"Liste {lid}"
            with get_conn() as conn:
                state = _batch_state(conn, cb)
                statut = state['statut'] if state else None
                if statut == 'pending':
                    continue  # réponse traitée par consume_approvals
                if statut in ('refuse', 'sent') and \
                        state['position'] == position and state['count'] == count:
                    continue  # lot inchangé → ne pas re-demander
                if send_validation_request is None:
                    logger.warning("[relance_batch] hub Telegram absent — lot non demandé")
                    return {'success': False, 'requests': requests}
                preview = (
                    f"*Relance {position} — {nom} ({count} prospects)*\n"
                    f"Campagne : {camp['nom']}\n"
                    f"Liste : {nom}\n"
                    f"Prospects dus : {count}\n\n"
                    f"✅ Valider → envoie {count} relances\n"
                    f"❌ Refuser → ne rien envoyer"
                )
                try:
                    ok = send_validation_request(
                        outil=f"v2_batch_{cid}_{lid}", preview=preview,
                        callback_id=cb, timeout_minutes=_TIMEOUT_MINUTES,
                    )
                except Exception as e:
                    logger.error("[relance_batch] send_validation_request %s: %s", cb, e)
                    continue
                if ok != 'pending':
                    # 'timeout' = hub absent ou envoi échoué → ne pas créer de lot
                    continue
                _save_batch(conn, cb, cid, lid, position, count, 'pending')
            requests.append({'callback_id': cb, 'campagne_id': cid, 'liste_id': lid,
                             'position': position, 'count': count})
    return {'success': True, 'requests': requests}


def consume_approvals() -> dict:
    """Consomme les réponses ✅/❌ des lots pendants (poller 1 min).

    ✅ → `orchestration.run_relances(cid, liste_id=lid, approval='auto')` déclenche
    l'envoi des relances dues de la liste, puis le lot passe à `sent`.
    ❌ → le lot passe à `refuse` : aucune relance envoyée.
    """
    from core import orchestration
    from envoi.telegram_validation import get_status, mark_completed

    consumed = []
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT callback_id, campagne_id, liste_id FROM relance_batches "
            "WHERE statut = 'pending'"
        ).fetchall()
        for row in rows:
            cb = row['callback_id']
            status = get_status(cb)
            if status not in ('ok', 'no'):
                continue
            mark_completed(cb)
            if status == 'ok':
                res = orchestration.run_relances(
                    row['campagne_id'], limit_per_campagne=_BATCH_HIGH_LIMIT,
                    liste_id=row['liste_id'], approval='auto', manual=True,
                )
                conn.execute(
                    "UPDATE relance_batches SET statut='sent', updated_at=datetime('now') "
                    "WHERE callback_id = ?", (cb,))
                log_status = 'sent'
            else:
                res = {'success': True, 'total': 0}
                conn.execute(
                    "UPDATE relance_batches SET statut='refuse', updated_at=datetime('now') "
                    "WHERE callback_id = ?", (cb,))
                log_status = 'refuse'
            consumed.append({'callback_id': cb, 'statut': log_status,
                             'total': res.get('total'), 'runs': res.get('runs')})
    return {'success': True, 'consumed': consumed}


__all__ = ["ensure_batch_requests", "consume_approvals", "batch_callback"]