# -*- coding: utf-8 -*-
"""
services/sniper_sender_service.py — Envoi des emails Sniper step 1

Envoie les leads Sniper approuvés dans la limite du quota quotidien
(`planning_settings.sniper_daily_quota`).

Séparé du pipeline Maps pour ne pas polluer le quota/les stats Maps.

Flux :
  1. Compte les step1 envoyés aujourd'hui (emails_envoyes + source Sniper)
  2. Calcule le reste disponible (quota - déjà envoyés)
  3. Sélectionne les leads_audites : statut_prospection='a_contacter', approuve=1
     ordonnés par score_urgence DESC
  4. Envoie via resend_sender.send_prospecting_email
  5. UPDATE statut_prospection='step1_envoye' + INSERT emails_envoyes

Usage scheduler (08:30) :
    from services.sniper_sender_service import send_sniper_step1
    send_sniper_step1()
"""

import logging
import threading

logger = logging.getLogger(__name__)

_SNIPER_SOURCES = ("ads", "fb_ads", "ecom", "tech", "jobs", "bodacc")

_job = {
    "running": False,
    "total":   0,
    "success": 0,
    "failed":  0,
}


def get_sniper_job_status() -> dict:
    return dict(_job)


# ─── Quota ────────────────────────────────────────────────────────────────────

def get_sniper_daily_quota() -> int:
    """Lit sniper_daily_quota depuis planning_settings (défaut : 20)."""
    try:
        from database.connection import get_conn
        with get_conn() as conn:
            row = conn.execute(
                "SELECT value FROM planning_settings WHERE key='sniper_daily_quota'"
            ).fetchone()
        return int(row["value"]) if row else 20
    except Exception:
        return 20


def get_sniper_sent_today() -> int:
    """Nombre de step1 Sniper envoyés aujourd'hui (via emails_envoyes)."""
    try:
        from database.connection import get_conn
        with get_conn() as conn:
            row = conn.execute("""
                SELECT COUNT(*) as n
                FROM emails_envoyes ee
                JOIN leads_bruts lb ON lb.id = ee.lead_id
                WHERE lb.source IN ('ads', 'fb_ads', 'ecom', 'tech', 'jobs', 'bodacc')
                  AND DATE(ee.date_envoi) = DATE('now')
            """).fetchone()
        return row["n"] if row else 0
    except Exception:
        return 0


def get_sniper_quota_remaining() -> int:
    return max(0, get_sniper_daily_quota() - get_sniper_sent_today())


# ─── Sélection des leads à envoyer ───────────────────────────────────────────

def _get_leads_to_send(limit: int) -> list[dict]:
    """
    Retourne les leads Sniper prêts à envoyer.
    Critères :
      - statut_prospection = 'a_contacter'
      - approuve = 1
      - email_valide non vide
      - source IN Sniper sources
    """
    try:
        from database.connection import get_conn
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT
                    la.id        AS audit_id,
                    la.lead_id,
                    la.email_objet,
                    la.email_corps,
                    la.email_valide,
                    la.lien_rapport,
                    la.score_urgence,
                    la.ceo_prenom,
                    la.ceo_nom,
                    lb.nom       AS company_nom,
                    lb.source
                FROM leads_audites la
                JOIN leads_bruts lb ON lb.id = la.lead_id
                WHERE la.statut_prospection = 'a_contacter'
                  AND la.approuve = 1
                  AND la.email_valide IS NOT NULL
                  AND la.email_valide != ''
                  AND la.email_corps  IS NOT NULL
                  AND la.email_corps  != ''
                  AND lb.source IN ('ads', 'fb_ads', 'ecom', 'tech', 'jobs', 'bodacc')
                ORDER BY la.score_urgence DESC
                LIMIT ?
            """, (limit,)).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"_get_leads_to_send : {e}")
        return []


# ─── Envoi ────────────────────────────────────────────────────────────────────

def send_sniper_step1(dry_run: bool = False) -> dict:
    """
    Envoie les step 1 Sniper dans la limite du quota.

    Args:
        dry_run: si True, simule sans envoyer ni modifier la DB

    Returns:
        {"success": int, "failed": int, "skipped": int, "quota_remaining": int}
    """
    if _job["running"]:
        return {"error": "Envoi Sniper déjà en cours"}

    remaining = get_sniper_quota_remaining()
    if remaining <= 0:
        logger.info("Sniper — quota quotidien atteint, aucun envoi")
        return {"success": 0, "failed": 0, "skipped": 0, "quota_remaining": 0}

    leads = _get_leads_to_send(remaining)
    if not leads:
        logger.info("Sniper — aucun lead approuvé à envoyer")
        return {"success": 0, "failed": 0, "skipped": 0, "quota_remaining": remaining}

    _job.update({"running": True, "total": len(leads), "success": 0, "failed": 0})

    stats = {"success": 0, "failed": 0, "skipped": 0}

    try:
        from envoi.resend_sender import send_prospecting_email
        from database.connection import get_conn
        from database import insert_email_sent

        for lead in leads:
            audit_id  = lead["audit_id"]
            lead_id   = lead["lead_id"]
            email     = lead["email_valide"]
            objet     = lead["email_objet"] or ""
            corps     = lead["email_corps"] or ""
            lien      = lead["lien_rapport"] or "https://incidenx.com"
            nom       = lead.get("ceo_prenom") or lead.get("company_nom") or "équipe"

            if not email or not corps:
                stats["skipped"] += 1
                continue

            if dry_run:
                logger.info(f"[DRY RUN] Sniper step1 → {email} | {objet[:60]}")
                stats["success"] += 1
                continue

            try:
                result = send_prospecting_email(
                    prospect_email = email,
                    prospect_nom   = nom,
                    email_objet    = objet,
                    email_corps    = corps,
                    lien_rapport   = lien,
                    dry_run        = False,
                )
            except Exception as e:
                logger.error(f"Sniper send {email} : {e}")
                stats["failed"] += 1
                _job["failed"] += 1
                continue

            if result.get("success"):
                with get_conn() as conn:
                    conn.execute(
                        "UPDATE leads_audites SET statut_prospection='step1_envoye' WHERE id=?",
                        (audit_id,)
                    )
                    conn.execute(
                        "UPDATE leads_bruts SET statut='envoye' WHERE id=?",
                        (lead_id,)
                    )
                    conn.commit()

                insert_email_sent({
                    "lead_id":           lead_id,
                    "message_id_resend": result.get("message_id", ""),
                    "email_objet":       objet,
                    "email_corps":       corps,
                    "email_destinataire": email,
                    "lien_rapport":      lien,
                    "statut_envoi":      "envoye",
                })

                stats["success"] += 1
                _job["success"] += 1
                logger.info(f"Sniper step1 envoyé → {email} | {objet[:60]}")

            else:
                stats["failed"] += 1
                _job["failed"] += 1
                logger.warning(f"Sniper step1 échec → {email} : {result.get('erreur')}")

    except Exception as e:
        logger.error(f"send_sniper_step1 erreur critique : {e}")

    finally:
        _job["running"] = False

    stats["quota_remaining"] = get_sniper_quota_remaining()
    logger.info(
        f"Sniper step1 terminé — "
        f"{stats['success']} envoyés, {stats['failed']} échecs, "
        f"{stats['skipped']} ignorés | quota restant : {stats['quota_remaining']}"
    )
    return stats


def send_sniper_step1_async() -> tuple[bool, str]:
    """Lance send_sniper_step1 en thread daemon. Retourne (ok, message)."""
    if _job["running"]:
        return False, "Envoi Sniper déjà en cours"

    threading.Thread(target=send_sniper_step1, daemon=True, name="sniper-sender").start()
    return True, "Envoi Sniper step1 lancé"
