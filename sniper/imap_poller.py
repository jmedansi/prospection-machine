# -*- coding: utf-8 -*-
"""
sniper/imap_poller.py — Détection des réponses aux emails Sniper (step 1)

Lire sniper/README.md avant toute modification.

Flux :
  1. Connexion IMAP SSL à mail.incidenx.com:993
  2. Scan des emails UNSEEN dans INBOX (dernières 48h)
  3. Pour chaque email : match sender → leads_audites.email_valide (ou domain fallback)
  4. Filtrage OOO / bounce / auto-reply
  5. Mise à jour DB : statut_prospection='repondu', emails_envoyes.repondu=1
  6. Notification Telegram avec bouton "Envoyer step 2"
  7. Marquage IMAP : email lu (SEEN)

Configuration .env :
  IMAP_HOST=mail.incidenx.com
  IMAP_PORT=993
  IMAP_USER=jmedansi@incidenx.com
  IMAP_PASSWORD=...

Appelé par dashboard/scheduler.py toutes les 15 minutes.
Ne jamais appeler en boucle bloquante — utiliser run_poll() depuis un thread.
"""

import imaplib
import email
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

logger = logging.getLogger(__name__)

# ─── Patterns OOO / bounce / auto-reply ──────────────────────────────────────

_OOO_PATTERNS = [
    r"absence du bureau",
    r"hors du bureau",
    r"out of office",
    r"automatic(ally)? reply",
    r"réponse automatique",
    r"auto.?reply",
    r"vacation",
    r"congé",
    r"maill?er daemon",
    r"delivery (status )?notification",
    r"undeliverable",
    r"non.?remis",
    r"échec de la remise",
    r"mail delivery failed",
    r"bounce",
    r"noreply",
    r"no-reply",
    r"do.not.reply",
]

_OOO_RE = re.compile("|".join(_OOO_PATTERNS), re.IGNORECASE)


def _is_auto_reply(subject: str, from_addr: str, headers: dict) -> bool:
    """Retourne True si l'email est un auto-reply ou bounce."""
    # En-tête RFC standard
    if headers.get("Auto-Submitted", "no") not in ("no", ""):
        return True
    if "auto-replied" in headers.get("Auto-Submitted", "").lower():
        return True
    # X-Auto-Response-Suppress (Exchange)
    if headers.get("X-Auto-Response-Suppress"):
        return True
    # Sujet
    if _OOO_RE.search(subject or ""):
        return True
    # Adresse expéditeur
    if _OOO_RE.search(from_addr or ""):
        return True
    return False


def _decode_header_value(raw: str) -> str:
    """Décode un en-tête email encodé (RFC 2047)."""
    parts = decode_header(raw or "")
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded).strip()


def _extract_sender_email(from_header: str) -> Optional[str]:
    """Extrait l'adresse email depuis un champ From: (ex: 'Jean Dupont <jean@site.fr>')."""
    match = re.search(r"<([^>]+)>", from_header)
    if match:
        return match.group(1).strip().lower()
    # Adresse nue
    match = re.search(r"[\w.\-+]+@[\w.\-]+", from_header)
    if match:
        return match.group(0).strip().lower()
    return None


def _extract_domain(email_addr: str) -> str:
    """Extrait le domaine d'une adresse email."""
    if "@" in (email_addr or ""):
        return email_addr.split("@", 1)[1].lower()
    return ""


# ─── Recherche en DB ──────────────────────────────────────────────────────────

def _find_lead_by_sender(sender_email: str, sender_domain: str) -> Optional[dict]:
    """
    Cherche le lead Sniper dont l'email correspond à l'expéditeur.

    Priorité :
      1. Match exact sur email_valide (leads_audites)
      2. Match domaine sur site_web (leads_bruts) — fallback si email non validé

    Retourne un dict lead ou None.
    """
    from database.connection import get_conn

    with get_conn() as conn:
        # 1. Match exact email
        row = conn.execute("""
            SELECT la.id AS audit_id, la.lead_id, la.lien_rapport,
                   la.email_objet, la.statut_prospection,
                   la.ceo_prenom, la.ceo_nom, la.copywriting_mode,
                   lb.nom, lb.site_web, lb.email, la.email_valide
            FROM leads_audites la
            JOIN leads_bruts lb ON lb.id = la.lead_id
            WHERE lb.source IN ('ads', 'tech', 'jobs', 'maps')
              AND la.statut_prospection = 'step1_envoye'
              AND (
                LOWER(la.email_valide) = ?
                OR LOWER(lb.email) = ?
              )
            LIMIT 1
        """, (sender_email, sender_email)).fetchone()

        if row:
            return dict(row)

        # 2. Fallback domaine
        if sender_domain:
            row = conn.execute("""
                SELECT la.id AS audit_id, la.lead_id, la.lien_rapport,
                       la.email_objet, la.statut_prospection,
                       la.ceo_prenom, la.ceo_nom, la.copywriting_mode,
                       lb.nom, lb.site_web, lb.email, la.email_valide
                FROM leads_audites la
                JOIN leads_bruts lb ON lb.id = la.lead_id
                WHERE lb.source IN ('ads', 'tech', 'jobs', 'maps')
                  AND la.statut_prospection = 'step1_envoye'
                  AND LOWER(lb.site_web) LIKE ?
                LIMIT 1
            """, (f"%{sender_domain}%",)).fetchone()

            if row:
                return dict(row)

    return None


def _mark_as_replied(audit_id: int, lead_id: int):
    """Met à jour DB : statut_prospection='repondu', emails_envoyes.repondu=1."""
    from database.connection import get_conn
    now = datetime.now().isoformat()

    with get_conn() as conn:
        conn.execute(
            "UPDATE leads_audites SET statut_prospection='repondu' WHERE id=?",
            (audit_id,)
        )
        conn.execute("""
            UPDATE emails_envoyes
            SET repondu=1, date_reponse=?, type_reponse='reply'
            WHERE lead_id=? AND repondu=0
        """, (now, lead_id))
        conn.commit()

    logger.info(f"imap_poller: lead {lead_id} → statut_prospection=repondu")


# ─── Notification Telegram ────────────────────────────────────────────────────

def _notify_telegram_reply(lead: dict, sender_email: str, subject: str):
    """
    Envoie une notification Telegram indiquant qu'un lead a répondu.
    Le message contient le bouton "Envoyer step 2" via callback.
    """
    try:
        from core.config import ensure_env
        ensure_env()
        from core.telegram_adapter import send_validation_request

        audit_id   = lead["audit_id"]
        nom        = lead.get("ceo_prenom") or lead.get("nom") or "?"
        site       = lead.get("site_web") or ""
        mode       = lead.get("copywriting_mode") or "transfert"
        lien       = lead.get("lien_rapport") or "https://incidenx.com"

        mode_label = "✅ CEO validé" if mode == "direct" else "↩️ Transfert"

        preview = (
            f"*Réponse reçue — {nom}*\n"
            f"Site : {site}\n"
            f"Email : `{sender_email}`\n"
            f"Sujet : {subject[:80]}\n"
            f"Mode : {mode_label}\n"
            f"Rapport : {lien}\n\n"
            f"Appuyer sur ✅ pour envoyer l'email step 2 avec le lien rapport."
        )

        callback_id = f"sniper_step2_{audit_id}"
        send_validation_request(
            outil       = f"Sniper Step 2 — {nom}",
            preview     = preview,
            callback_id = callback_id,
            timeout_minutes = 2880,   # 48h — le commercial peut répondre plus tard
        )
        logger.info(f"imap_poller: Telegram envoyé pour lead {lead['lead_id']}")

    except Exception as e:
        logger.error(f"imap_poller: Telegram notification failed — {e}")


# ─── Connexion IMAP ───────────────────────────────────────────────────────────

def _get_imap_conn() -> imaplib.IMAP4_SSL:
    """Ouvre une connexion IMAP SSL. Lève une exception si .env incomplet."""
    from core.config import ensure_env
    ensure_env()

    host     = os.getenv("IMAP_HOST", "mail.incidenx.com")
    port     = int(os.getenv("IMAP_PORT", "993"))
    user     = os.getenv("IMAP_USER", "")
    password = os.getenv("IMAP_PASSWORD", "")

    if not user or not password:
        raise EnvironmentError("IMAP_USER / IMAP_PASSWORD manquants dans .env")

    mail = imaplib.IMAP4_SSL(host, port)
    mail.login(user, password)
    return mail


# ─── Poll principal ───────────────────────────────────────────────────────────

def run_poll(lookback_hours: int = 48) -> dict:
    """
    Scan IMAP pour les réponses aux emails Sniper step 1.

    Args:
        lookback_hours: Chercher dans les N dernières heures (défaut 48h)

    Returns:
        {"scanned": int, "matched": int, "notified": int, "errors": int}
    """
    stats = {"scanned": 0, "matched": 0, "notified": 0, "errors": 0}

    try:
        mail = _get_imap_conn()
    except Exception as e:
        logger.error(f"imap_poller: connexion impossible — {e}")
        stats["errors"] += 1
        return stats

    try:
        mail.select("INBOX")

        # Critère de recherche : emails non lus depuis lookback_hours
        since_dt  = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
        since_str = since_dt.strftime("%d-%b-%Y")
        _, msg_ids = mail.search(None, f'(UNSEEN SINCE "{since_str}")')

        ids = msg_ids[0].split() if msg_ids[0] else []
        logger.info(f"imap_poller: {len(ids)} emails UNSEEN depuis {lookback_hours}h")

        for uid in ids:
            stats["scanned"] += 1
            try:
                _, data = mail.fetch(uid, "(RFC822)")
                raw = data[0][1]
                msg = email.message_from_bytes(raw)

                # En-têtes
                from_raw  = msg.get("From", "")
                subject   = _decode_header_value(msg.get("Subject", ""))
                headers   = {k: msg.get(k, "") for k in (
                    "Auto-Submitted", "X-Auto-Response-Suppress",
                    "Precedence", "X-Mailer",
                )}

                sender_email  = _extract_sender_email(from_raw) or ""
                sender_domain = _extract_domain(sender_email)

                # Filtrer OOO / auto-replies
                if _is_auto_reply(subject, sender_email, headers):
                    logger.debug(f"imap_poller: OOO ignoré — {sender_email}")
                    # Marquer comme lu quand même pour ne plus le traiter
                    mail.store(uid, "+FLAGS", "\\Seen")
                    continue

                # Chercher le lead correspondant
                lead = _find_lead_by_sender(sender_email, sender_domain)
                if not lead:
                    logger.debug(f"imap_poller: pas de match — {sender_email}")
                    continue

                stats["matched"] += 1
                logger.info(
                    f"imap_poller: réponse détectée — {sender_email} "
                    f"→ lead {lead['lead_id']} ({lead.get('nom', '?')})"
                )

                # Mettre à jour la DB
                _mark_as_replied(lead["audit_id"], lead["lead_id"])

                # Notification Telegram
                _notify_telegram_reply(lead, sender_email, subject)
                stats["notified"] += 1

                # Marquer comme lu
                mail.store(uid, "+FLAGS", "\\Seen")

            except Exception as e:
                logger.error(f"imap_poller: erreur traitement email {uid} — {e}")
                stats["errors"] += 1

    finally:
        try:
            mail.logout()
        except Exception:
            pass

    logger.info(
        f"imap_poller: terminé — "
        f"{stats['scanned']} scannés, {stats['matched']} matchés, "
        f"{stats['notified']} notifiés, {stats['errors']} erreurs"
    )
    return stats


# ─── Envoi step 2 (déclenché par callback Telegram) ──────────────────────────

def send_step2(audit_id: int) -> bool:
    """
    Envoie l'email step 2 (livraison du rapport) pour un lead qui a répondu.

    Appelé par le webhook Telegram quand le bouton "Envoyer step 2" est pressé.

    Args:
        audit_id: ID dans leads_audites

    Returns:
        True si envoyé, False sinon
    """
    from database.connection import get_conn
    from core.config import ensure_env
    ensure_env()

    try:
        with get_conn() as conn:
            row = conn.execute("""
                SELECT la.id, la.lead_id, la.lien_rapport,
                       la.ceo_prenom, la.ceo_nom, la.email_valide,
                       la.statut_prospection,
                       lb.nom, lb.site_web, lb.email, lb.source
                FROM leads_audites la
                JOIN leads_bruts lb ON lb.id = la.lead_id
                WHERE la.id = ?
            """, (audit_id,)).fetchone()

        if not row:
            logger.error(f"send_step2: audit_id {audit_id} introuvable")
            return False

        lead = dict(row)

        if lead["statut_prospection"] == "lien_envoye":
            logger.warning(f"send_step2: step 2 déjà envoyé pour audit {audit_id}")
            return False

        # Publier le rapport sur GitHub avant d'envoyer l'email
        from dashboard.pipeline.report_publishing import _publish_reports
        published_urls = _publish_reports([lead["lead_id"]])
        if lead["lead_id"] in published_urls:
            lien = published_urls[lead["lead_id"]]
            logger.info(f"send_step2: Rapport publié sur GitHub: {lien}")
        else:
            logger.warning(f"send_step2: Échec publication rapport pour lead {lead['lead_id']}, utilisation lien existant")
            lien = lead.get("lien_rapport") or "https://incidenx.com"

        # Charger le template step 2 selon la source
        import os
        source = lead.get("source", "")
        if source == "maps":
            template_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "templates", "emails", "email_step2_maps.html",
            )
        else:
            template_path = os.path.join(
                os.path.dirname(__file__), "templates", "email_step2_livraison.html"
            )
        with open(template_path, encoding="utf-8") as f:
            html = f.read()

        nom         = lead.get("ceo_prenom") or lead.get("nom") or ""
        site        = lead.get("site_web") or ""
        lien_cal    = os.getenv("CALENDLY_URL", "https://calendly.com/jmedansi")
        dest_email  = lead.get("email_valide") or lead.get("email") or ""

        if not dest_email:
            logger.error(f"send_step2: pas d'email destinataire pour audit {audit_id}")
            return False

        html = (html
            .replace("{{NOM}}", nom)
            .replace("{{SITE}}", site)
            .replace("{{LIEN_RAPPORT}}", lien)
            .replace("{{LIEN_CALENDLY}}", lien_cal)
        )

        subject = f"Votre rapport d'audit — {site}"

        # Envoi via Resend (réutilise le sender existant)
        from envoi.resend_sender import send_prospecting_email
        result = send_prospecting_email(
            prospect_email = dest_email,
            prospect_nom   = nom,
            email_objet    = subject,
            email_corps    = html,
        )
        ok = result.get("success", False)

        if ok:
            with get_conn() as conn:
                conn.execute(
                    "UPDATE leads_audites SET statut_prospection='lien_envoye' WHERE id=?",
                    (audit_id,)
                )
                conn.commit()
            logger.info(f"send_step2: step 2 envoyé → {dest_email} (audit {audit_id})")
            return True

        return False

    except Exception as e:
        logger.error(f"send_step2({audit_id}) → {e}")
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    result = run_poll(lookback_hours=48)
    print(result)
