# -*- coding: utf-8 -*-
"""
core/bounce_handler.py — File de traitement des bounces et plaintes (délivrabilité).

Flux :
    webhook Resend (`email.bounced` / `email.complained`)
        → `suppression_list` (déjà posé par webhooks._suppress_recipient)
        → record_bounce()            : ligne `bounce_queue` + notif Telegram ✅/❌
    poller `v2_bounce_poll` (1 min)
        → consume_bounce_approvals() :
              ✅ → archive_bounce()  : `ne_plus_contacter` + déplacement 🗑 Corbeille
              ❌ → ignore_bounce()   : la ligne passe à `ignore`
    alternatif (UI « Suivi ») : mêmes deux actions via
        POST /api/v2/bounces/<id>/archive  et  /api/v2/bounces/<id>/ignore

État persisté dans `bounce_queue` (voir schema.migrate_bounce_queue) :
    pending  → demande envoyée, en attente de décision
    traite   → ✅ consommé : prospect blacklisté + déplacé en Corbeille
    ignore   → ❌ : `suppression_list` inchangée, aucun mouvement de prospect
"""
import logging

from database.connection import get_conn

logger = logging.getLogger(__name__)

_TIMEOUT_MINUTES = 2880  # 48h, cohérent avec la validation par prospect

# raison → libellé affiché dans la notif / le bloc Suivi
_MOTIFS = {
    'bounce_dur': ('📧 Bounce email', 'Bounce dur — adresse inutilisable'),
    'plainte':    ('🚫 Plainte spam', 'L\'utilisateur a signalé le message en spam'),
}


def callback_id(bounce_id: int) -> str:
    return f"v2_bounce_{int(bounce_id)}"


def _motif(raison: str) -> tuple[str, str]:
    return _MOTIFS.get(raison, (_MOTIFS['bounce_dur'][0], raison))


def _md(text) -> str:
    """Échappe les caractères Markdown legacy de Telegram (`parse_mode="Markdown"`).

    Sans échappement, un email comme `chef_45@legourmet.fr` (un seul `_`) casse le
    parseur → « Can't parse entities » et la demande ✅/❌ n'est JAMAIS envoyée.
    """
    s = str(text or '')
    for ch in ('_', '*', '`', '['):
        s = s.replace(ch, '\\' + ch)
    return s



def _normalize(email: str) -> str:
    return (email or '').strip().lower()


def _resolve_prospect(email: str) -> dict | None:
    """Rattache l'adresse à un prospect v2 (dernier import) + sa campagne/liste."""
    addr = _normalize(email)
    if '@' not in addr:
        return None
    with get_conn() as conn:
        row = conn.execute(
            """SELECT p.id AS prospect_id, p.liste_id, l.campagne_id, p.nom, p.prenom,
                      p.entreprise, p.email
               FROM prospects p JOIN listes l ON p.liste_id = l.id
               WHERE LOWER(TRIM(p.email)) = ?
               ORDER BY p.id DESC LIMIT 1""",
            (addr,),
        ).fetchone()
        if not row:
            return None
        return dict(row)


# ── Enregistrement + notification ─────────────────────────────────────────────

def record_bounce(email: str, *, raison: str = 'bounce_dur', motif: str | None = None,
                  email_record_id: int | None = None, notify: bool = True) -> dict:
    """Pose la ligne `bounce_queue` et envoie la notif Telegram ✅/❌ (une fois).

    Idempotent : un re-bounce (retry de webhook) sur une adresse déjà `pending`
    ou déjà statuée ne renvoie JAMAIS une seconde demande.
    `notify=False` diffère l'envoi (décision groupée appelée via `notify_pending`).
    """
    addr = _normalize(email)
    if '@' not in addr or addr.startswith('@') or addr.endswith('@'):
        return {'success': False, 'error': 'adresse invalide', 'notified': False}

    prosp = _resolve_prospect(addr) or {}
    with get_conn() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO bounce_queue
               (email, email_record_id, prospect_id, campagne_id, liste_id, motif, raison, statut)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')""",
            (addr, email_record_id, prosp.get('prospect_id'), prosp.get('campagne_id'),
             prosp.get('liste_id'), motif, raison),
        )
        if motif:
            conn.execute(
                "UPDATE bounce_queue SET motif = COALESCE(motif, ?) WHERE email = ?",
                (motif, addr),
            )
        row = conn.execute(
            "SELECT id, statut, callback_id FROM bounce_queue WHERE email = ?", (addr,)
        ).fetchone()
        conn.commit()

    if not row:
        return {'success': False, 'error': 'ligne non créée', 'notified': False}
    bounce_id, statut, cb = row['id'], row['statut'], row['callback_id']
    if statut != 'pending' or cb:
        # déjà notifiée (en attente) ou déjà statuée → pas de doublon
        return {'success': True, 'bounce_id': bounce_id, 'statut': statut, 'notified': False,
                'needs_notify': False}
    if not notify:
        return {'success': True, 'bounce_id': bounce_id, 'statut': statut, 'notified': False,
                'needs_notify': True}

    notified = _notify(bounce_id, raison, prosp, addr)
    return {'success': True, 'bounce_id': bounce_id, 'statut': statut, 'notified': bool(notified),
            'needs_notify': False}


def notify_pending(bounce_ids: list[int]) -> int:
    """Envoie les notifs ✅/❌ d'un lot différé (`record_bounce(notify=False)`).

    UN message Telegram par bounce, avec sa propre paire de boutons ✅/❌.
    Retourne le nombre de notifications envoyées.
    """
    if not bounce_ids:
        return 0
    with get_conn() as conn:
        placeholders = ','.join('?' * len(bounce_ids))
        rows = [dict(r) for r in conn.execute(
            f"SELECT id, email, raison, callback_id, statut FROM bounce_queue "
            f"WHERE id IN ({placeholders})", bounce_ids).fetchall()]
    rows = [r for r in rows if r['statut'] == 'pending' and not r['callback_id']]

    sent = 0
    for r in rows:
        prosp = _resolve_prospect(r['email']) or {}
        if _notify(r['id'], r['raison'], prosp, r['email']):
            sent += 1
    return sent


def _notify(bounce_id: int, raison: str, prosp: dict, email: str) -> bool:
    """Envoie la demande Telegram ✅/❌. Jamais bloquant (fallback no-op)."""
    cb = callback_id(bounce_id)
    titre, legende = _motif(raison)
    nom = (prosp.get('entreprise') or prosp.get('nom') or '').strip() or '?'
    lignes = [
        f"*{_md(titre)}*",
        f"Adresse : {_md(email)}",
        f"Motif : {_md(legende)}",
        f"Société : {_md(nom)}",
        f"Prospect : #{prosp.get('prospect_id') or '—'} · campagne {prosp.get('campagne_id') or '—'}",
        "",
        "✅ → 🗑 Corbeille (ne plus contacter)",
        "❌ → Ignorer (l'adresse reste bloquée)",
    ]
    if not prosp.get('prospect_id'):
        lignes.insert(4, "⚠️ Aucun prospect v2 rattaché à cette adresse.")
    try:
        from core.telegram_adapter import send_validation_request
        ok = send_validation_request(
            outil=f"v2_bounce_{bounce_id}", preview="\n".join(lignes),
            callback_id=cb, timeout_minutes=_TIMEOUT_MINUTES,
        )
    except Exception as e:
        logger.error("[bounce] send_validation_request %s: %s", cb, e)
        return False
    if ok != 'pending':
        logger.warning("[bounce] notification %s non acceptée (%s)", cb, ok)
        return False
    with get_conn() as conn:
        conn.execute(
            "UPDATE bounce_queue SET callback_id = ?, statut = 'pending', updated_at = datetime('now') "
            "WHERE id = ?",
            (cb, bounce_id),
        )
        conn.commit()
    logger.info("[bounce] notif Telegram envoyée %s", cb)
    return True


# ── Consultation (UI « Suivi ») ───────────────────────────────────────────────

def list_bounces(campagne_id: int | None = None, statut: str | None = 'pending') -> list[dict]:
    with get_conn() as conn:
        sql = (
            "SELECT b.id, b.email, b.motif, b.raison, b.statut, b.prospect_id, b.campagne_id, "
            "b.created_at, b.updated_at, "
            "p.nom, p.prenom, p.entreprise, p.statut AS prospect_statut, "
            "l.nom AS liste_nom, c.nom AS campagne_nom "
            "FROM bounce_queue b "
            "LEFT JOIN prospects p ON p.id = b.prospect_id "
            "LEFT JOIN listes l ON l.id = p.liste_id "
            "LEFT JOIN campagnes c ON c.id = b.campagne_id "
            "WHERE 1=1"
        )
        params: list = []
        if statut:
            sql += " AND b.statut = ?"
            params.append(statut)
        if campagne_id:
            sql += " AND (b.campagne_id = ? OR p.liste_id IN (SELECT id FROM listes WHERE campagne_id = ?))"
            params += [campagne_id, campagne_id]
        sql += " ORDER BY b.created_at DESC, b.id DESC LIMIT 300"
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_bounce(bounce_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM bounce_queue WHERE id = ?", (int(bounce_id),)).fetchone()
    return dict(row) if row else None


# ── Actions (boutons Telegram et UI) ──────────────────────────────────────────

def archive_bounce(bounce_id: int) -> dict:
    """✅ : `ne_plus_contacter` (suppression_list + transition) + déplacement 🗑 Corbeille."""
    from database import prospects as prospects_repo
    from database.listes import get_or_create_corbeille, unlink_prospects

    bounce = get_bounce(bounce_id)
    if not bounce:
        return {'success': False, 'error': 'Bounce introuvable'}
    if bounce['statut'] == 'traite':
        return {'success': True, 'statut': 'traite', 'deja_traite': True}
    if bounce['statut'] == 'ignore':
        return {'success': False, 'error': 'Bounce déjà ignoré — réutilisez le bouton de la campagne'}

    pid = bounce.get('prospect_id')
    campagne_id = bounce.get('campagne_id')
    moved = 0
    if pid:
        # 1. opposition au contact : flag + suppression_list GLOBALE + transition finale
        res = prospects_repo.set_ne_plus_contacter(int(pid), True, raison=bounce.get('raison') or 'bounce_dur')
        if not res.get('success'):
            logger.warning("[bounce] set_ne_plus_contacter #%s: %s", pid, res.get('error'))
        else:
            # 2. déplacement non destructif vers la 🗑 Corbeille de la campagne
            try:
                if campagne_id:
                    get_or_create_corbeille(int(campagne_id))
                prosp = prospects_repo.get_prospect(int(pid)) or {}
                liste_id = prosp.get('liste_id') or bounce.get('liste_id')
                if liste_id:
                    r = unlink_prospects(int(liste_id), [int(pid)])
                    moved = r.get('moved', 0) if r.get('success') else 0
            except Exception as e:
                logger.error("[bounce] déplacement corbeille #%s: %s", pid, e)

    with get_conn() as conn:
        conn.execute(
            "UPDATE bounce_queue SET statut = 'traite', updated_at = datetime('now') WHERE id = ?",
            (int(bounce_id),),
        )
        conn.commit()
    logger.info("[bounce] #%s archivé (prospect=%s, corbeille=%s)", bounce_id, pid, moved)
    return {'success': True, 'statut': 'traite', 'prospect_id': pid, 'moved': moved}


def ignore_bounce(bounce_id: int) -> dict:
    """❌ : aucun mouvement. `suppression_list` conserve le blocage d'envoi."""
    bounce = get_bounce(bounce_id)
    if not bounce:
        return {'success': False, 'error': 'Bounce introuvable'}
    if bounce['statut'] == 'traite':
        return {'success': False, 'error': 'Bounce déjà archivé en Corbeille'}
    with get_conn() as conn:
        conn.execute(
            "UPDATE bounce_queue SET statut = 'ignore', updated_at = datetime('now') WHERE id = ?",
            (int(bounce_id),),
        )
        conn.commit()
    return {'success': True, 'statut': 'ignore'}


# ── Poller ────────────────────────────────────────────────────────────────────

def consume_bounce_approvals() -> dict:
    """Consomme les réponses ✅/❌ des bounces pendants (poller 1 min)."""
    from envoi.telegram_validation import get_status, mark_completed

    consumed = []
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, callback_id FROM bounce_queue WHERE statut = 'pending' AND callback_id IS NOT NULL"
        ).fetchall()
    for row in rows:
        cb = row['callback_id']
        try:
            status = get_status(cb)
        except Exception as e:
            logger.error("[bounce] get_status %s: %s", cb, e)
            continue
        if status not in ('ok', 'no'):
            continue
        try:
            mark_completed(cb)
            if status == 'ok':
                res = archive_bounce(row['id'])
            else:
                res = ignore_bounce(row['id'])
            consumed.append({'bounce_id': row['id'], 'callback_id': cb,
                             'answer': status, 'success': bool(res.get('success')),
                             'moved': res.get('moved', 0), 'error': res.get('error')})
        except Exception as e:
            logger.error("[bounce] consumption %s: %s", cb, e)
    if consumed:
        logger.info("[bounce] %s décision(s) consommée(s)", len(consumed))
    return {'success': True, 'consumed': consumed}


__all__ = ["callback_id", "record_bounce", "notify_pending", "list_bounces", "get_bounce",
           "archive_bounce", "ignore_bounce", "consume_bounce_approvals"]
