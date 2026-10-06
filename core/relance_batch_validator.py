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
    sending  → lot réclamé par un poll (verrou atomique), envoi en cours
    sent     → ✅ consommé, relances envoyées
    refuse   → ❌ : aucune relance envoyée ; pas de re-demande tant que la position
               ET le nombre de prospects à relancer restent inchangés.
    erreur   → ✅ consommée mais envoi en échec technique (après `_MAX_TENTATIVES`) :
               aucune relance envoyée, pas de re-demande automatique non plus —
               revalidation manuelle requise (bouton « Valider »).
"""
import logging

from database.connection import get_conn

logger = logging.getLogger(__name__)

_BATCH_HIGH_LIMIT = 500  # un lot validé lance TOUTE la liste (pas de plafond de 20)
_TIMEOUT_MINUTES = 2880  # 48h, cohérent avec la validation par prospect
_MAX_TENTATIVES = 3      # échecs techniques de suite avant de clore le lot
_SENDING_ORPHELIN_MIN = 10  # un lot 'sending' plus vieux que ça = process mort


def _md(text) -> str:
    """Échappe le Markdown legacy de Telegram (`parse_mode="Markdown"`).

    Un nom de liste ou de campagne contenant `_`, `*`, `` ` `` ou `[` fait échouer
    le parseur (« Can't parse entities ») et la demande ✅/❌ n'est JAMAIS envoyée.
    Même garde que `core.bounce_handler._md`.
    """
    s = str(text or '')
    for ch in ('_', '*', '`', '['):
        s = s.replace(ch, '\\' + ch)
    return s


def batch_callback(campagne_id: int, liste_id: int) -> str:
    return f"v2_batch_{int(campagne_id)}_{int(liste_id)}"


def _batch_state(conn, callback_id_value: str):
    row = conn.execute(
        "SELECT campagne_id, liste_id, position, count, statut, tentatives FROM relance_batches "
        "WHERE callback_id = ?",
        (callback_id_value,),
    ).fetchone()
    return dict(row) if row else None


def _read_batch(callback_id_value: str):
    """`_batch_state` en LECTURE SEULE (transaction courte, libérée aussitôt)."""
    conn = get_conn()
    try:
        return _batch_state(conn, callback_id_value)
    finally:
        conn.close()


def _save_batch(callback_id_value: str, campagne_id: int, liste_id: int,
                position: int, count: int, statut: str):
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO relance_batches (callback_id, campagne_id, liste_id, position,
                                            count, statut, tentatives, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 0, datetime('now'))
               ON CONFLICT(callback_id) DO UPDATE SET
                   campagne_id = excluded.campagne_id,
                   liste_id    = excluded.liste_id,
                   position    = excluded.position,
                   count       = excluded.count,
                   statut      = excluded.statut,
                   tentatives  = 0,
                   updated_at  = datetime('now')""",
            (callback_id_value, int(campagne_id), int(liste_id), int(position),
             int(count), statut),
        )
        conn.commit()
    finally:
        conn.close()


def _set_batch_statut(callback_id_value: str, statut: str):
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE relance_batches SET statut=?, updated_at=datetime('now') WHERE callback_id=?",
            (statut, callback_id_value))
        conn.commit()
    finally:
        conn.close()


def _claim_batch(callback_id_value: str) -> int | None:
    """Réclame atomiquement un lot `pending` (`pending` → `sending`, +1 tentative).

    Retourne le numéro de tentative, ou None si un autre poll a déjà réclamé le lot.
    La transaction est COMMITée et la connexion FERMÉE avant de retourner : la
    laisser ouverte autour de `run_relances()` verrouillerait l'écriture de toute
    la base pendant l'envoi (cf. `database is locked`, 2026-10-01).
    """
    conn = get_conn()
    try:
        claim = conn.execute(
            "UPDATE relance_batches SET statut='sending', "
            "tentatives=COALESCE(tentatives, 0) + 1, updated_at=datetime('now') "
            "WHERE callback_id = ? AND statut = 'pending'", (callback_id_value,))
        if claim.rowcount != 1:
            conn.rollback()
            return None
        row = conn.execute(
            "SELECT COALESCE(tentatives, 0) FROM relance_batches WHERE callback_id = ?",
            (callback_id_value,)).fetchone()
        tentatives = int(row[0]) if row else 1
        conn.commit()
        return tentatives
    finally:
        conn.close()


def _reset_sending_orphelins():
    """Relance les lots restés `sending` (process mort en plein envoi).

    `run_relances` est idempotent (un prospect déjà en `relance_k` n'est plus dû) :
    rejouer le lot ne renvoie donc pas deux fois le même email.
    """
    conn = get_conn()
    try:
        cur = conn.execute(
            "UPDATE relance_batches SET statut='pending', updated_at=datetime('now') "
            "WHERE statut='sending' AND updated_at < datetime('now', ?)",
            (f"-{_SENDING_ORPHELIN_MIN} minutes",))
        n = cur.rowcount
        if n:
            conn.commit()
            logger.warning("[relance_batch] %d lot(s) 'sending' orphelin(s) remis en attente", n)
        return n
    finally:
        conn.close()


def ensure_batch_requests(campagne_id: int = None, liste_id: int = None,
                          force: bool = False) -> dict:
    """Pour chaque campagne `validation_relances=1`, demande un ✅ par liste ayant des
    relances dues.

    Idempotent : ne renvoie jamais une demande déjà `pending` (réponse traitée par
    `consume_approvals`), et ne redemande pas un lot `refuse`/`sent`/`erreur` tant
    que sa position ET son count n'ont pas changé.

    - `campagne_id` / `liste_id` : ne traiter QUE cette campagne / cette liste. Sans
      filtre, un clic sur le bouton « Déclencher Telegram » d'une liste Balayait
      toutes les autres listes dues → une notification par liste.
    - `force=True` : re-demande explicite (bouton de l'UI) — ré-autorise un lot
      `refuse`/`sent`/`erreur` inchangé. Un lot `pending` reste ignoré (une demande
      est déjà dans la boîte : en renvoyer une autre ne ferait que du bruit).

    HORS FENÊTRE HORAIRE (`orchestration.is_fenetre_relances`) : aucune demande
    n'est envoyée — sinon le job 10 min notifiait le plein milieu de la nuit.
    """
    from core import orchestration
    from envoi.telegram_validation import get_status
    try:
        from core.telegram_adapter import send_validation_request
    except Exception:
        send_validation_request = None

    if not orchestration.is_fenetre_relances():
        logger.info("[relance_batch] hors fenêtre horaire — demandes différées")
        return {'success': True, 'requests': [], 'differee': True}

    campagnes = [c for c in orchestration.enabled_campagnes() if c.get('validation_relances')]
    if campagne_id:
        campagnes = [c for c in campagnes if int(c['id']) == int(campagne_id)]
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
            if liste_id and int(lid) != int(liste_id):
                continue
            cb = batch_callback(cid, lid)
            position = cands[0]['position']
            count = len(cands)
            nom = cands[0].get('liste_nom') or f"Liste {lid}"
            state = _read_batch(cb)
            statut = state['statut'] if state else None
            if statut in ('pending', 'sending'):
                continue  # réponse traitée (ou en cours d'envoi) par consume_approvals
            if not force and statut in ('refuse', 'sent', 'erreur') and \
                    state['position'] == position and state['count'] == count:
                continue  # lot inchangé → ne pas re-demander
            # Le hub contient déjà une demande pour CE callback mais le lot a été
            # supprimé (bouton « Valider » de l'UI) : on réenregistre le lot SANS
            # renvoyer de message, sinon la ✅ déjà donnée par l'utilisateur ne
            # serait consommée par personne (« rien n'est parti »).
            hub_status = None
            try:
                hub_status = get_status(cb)
            except Exception:
                hub_status = None
            if hub_status in ('ok', 'no', 'pending'):
                _save_batch(cb, cid, lid, position, count, 'pending')
                requests.append({'callback_id': cb, 'campagne_id': cid, 'liste_id': lid,
                                 'position': position, 'count': count,
                                 'reuse': hub_status})
                continue
            if send_validation_request is None:
                logger.warning("[relance_batch] hub Telegram absent — lot non demandé")
                return {'success': False, 'requests': requests}
            titre = f"📲 Relances — {_md(nom)}"
            preview = (
                f"*{_md(camp['nom'])}*\n"
                f"{'─' * 20}\n"
                f"Liste : {_md(nom)}\n"
                f"Touche : relance {position}\n"
                f"Prospects à relancer : *{count}*\n\n"
                f"✅ *Valider* → envoi des {count} relances\n"
                f"❌ *Refuser* → aucun envoi\n\n"
                f"_Valable 48 h (fenêtre d'envoi 9 h – 18 h, jours ouvrés)._"
            )
            # Appel réseau HORS transaction : une transaction d'écriture tenue
            # pendant l'appel Telegram verrouille la base pour tous les autres
            # reqteurs (webhooks Resend, jobs scheduler…).
            try:
                # `outil` est stocké tel quel dans pending.db et renvoyé par bot.py
                # (message de confirmation) en texte PLAIN → jamais de Markdown
                # échappé ici, sinon un nom avec `_` ressort avec des antislashs.
                ok = send_validation_request(
                    outil=f"Relances — {nom}", preview=preview,
                    callback_id=cb, timeout_minutes=_TIMEOUT_MINUTES, titre=titre,
                )
            except Exception as e:
                logger.error("[relance_batch] send_validation_request %s: %s", cb, e)
                continue
            if ok != 'pending':
                # 'timeout' = hub absent ou envoi échoué → ne pas créer de lot
                continue
            _save_batch(cb, cid, lid, position, count, 'pending')
            requests.append({'callback_id': cb, 'campagne_id': cid, 'liste_id': lid,
                             'position': position, 'count': count})
    return {'success': True, 'requests': requests}


def consume_approvals() -> dict:
    """Consomme les réponses ✅/❌ des lots pendants (poller 1 min).

    ✅ → `orchestration.run_relances(cid, liste_id=lid, approval='auto')` déclenche
    l'envoi des relances dues de la liste, puis le lot passe à `sent`.
    ❌ → le lot passe à `refuse` : aucune relance envoyée.

    Hors fenêtre horaire : RIEN n'est consommé — la ✅ reste en attente et partira
    à l'ouverture de la fenêtre (jamais d'envoi la nuit).

    Erreur technique pendant l'envoi : le lot est remis `pending` (la ✅ n'est PAS
    consommée) et rejoué au poll suivant, jusqu'à `_MAX_TENTATIVES` ; au-delà le
    lot passe `erreur` et attend une revalidation manuelle. Une ✅ n'est donc jamais
    perdue sur un échec technique (2026-10-01 : verrou SQLite → 21 relances
    perdues, lot clos `refuse`, jamais re-demandé).
    """
    from core import orchestration
    from envoi.telegram_validation import get_status, mark_completed

    if not orchestration.is_fenetre_relances():
        logger.info("[relance_batch] hors fenêtre horaire — réponses différées")
        return {'success': True, 'consumed': [], 'differee': True}

    _reset_sending_orphelins()

    conn = get_conn()
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT callback_id, campagne_id, liste_id FROM relance_batches "
            "WHERE statut = 'pending'").fetchall()]
    finally:
        conn.close()

    consumed = []
    for row in rows:
        cb = row['callback_id']
        status = get_status(cb)
        if status not in ('ok', 'no'):
            continue
        # Réclamation ATOMIQUE : avec plusieurs scheduler en concurrence, deux
        # processus lisaient le même lot `pending` et lançaient deux `run_relances`
        # simultanés (relance_1 puis relance_2 en quelques secondes). La
        # transaction est commitée ici : `run_relances` s'exécute ensuite SANS
        # aucun verrou d'écriture tenu par ce poll.
        tentatives = _claim_batch(cb)
        if tentatives is None:
            continue  # déjà réclamé par un autre processus
        try:
            if status == 'ok':
                res = orchestration.run_relances(
                    row['campagne_id'], limit_per_campagne=_BATCH_HIGH_LIMIT,
                    liste_id=row['liste_id'], approval='auto', manual=True,
                )
            else:
                res = {'success': True, 'total': 0}
        except Exception as e:
            if tentatives < _MAX_TENTATIVES:
                _set_batch_statut(cb, 'pending')
                logger.error(
                    "[relance_batch] %s : échec pendant l'envoi (%s) — tentative %d/%d, "
                    "nouvel essai au prochain poll (✅ non consommée)",
                    cb, e, tentatives, _MAX_TENTATIVES)
                continue
            _set_batch_statut(cb, 'erreur')
            mark_completed(cb)
            logger.error(
                "[relance_batch] %s : échec définitif après %d tentatives (%s) — "
                "aucune relance envoyée, revalidation manuelle requise",
                cb, tentatives, e)
            continue
        mark_completed(cb)
        log_status = 'sent' if status == 'ok' else 'refuse'
        _set_batch_statut(cb, log_status)
        consumed.append({'callback_id': cb, 'statut': log_status,
                         'total': res.get('total'), 'runs': res.get('runs')})
    return {'success': True, 'consumed': consumed}


__all__ = ["ensure_batch_requests", "consume_approvals", "batch_callback"]