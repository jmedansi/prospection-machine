# -*- coding: utf-8 -*-
"""
dashboard/pipeline.py
Pipeline soirée (20h) : sélection leads → audit → email → validation Telegram → approbation.

Flux :
  1. Sélectionner jusqu'à 60 leads avec email, non encore envoyés
  2. Lancer l'audit pour ceux qui n'en ont pas
  3. Générer le copywriting email via les fonctions SQLite du copywriter
  4. Envoyer une demande de validation Telegram pour les AUDITS (timeout 5h)
  5. Si validé (ou auto-validé) : demande de validation Telegram pour les EMAILS
  6. Si validé (ou auto-validé) : marquer approuve=1 → envoi demain 8h + 17h
"""
import os
import sys
import uuid
import json
import logging
import subprocess
import threading
from datetime import datetime, timedelta

try:
    import pytz
    TZ = pytz.timezone('Europe/Paris')
except ImportError:
    from datetime import timezone
    TZ = timezone.utc  # fallback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
HUB_TELEGRAM = 'D:/hub_telegram'
sys.path.insert(0, HUB_TELEGRAM)

from database.db_manager import get_conn

logger = logging.getLogger(__name__)


def _get_setting(key, default=None):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM planning_settings WHERE key=?", (key,)).fetchone()
        return row['value'] if row else default

def _set_setting(key, value):
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO planning_settings (key, value) VALUES (?, ?)", (key, str(value)))
        conn.commit()


# ──────────────────────────────────────────────────────────────────────────────
# SÉLECTION DES LEADS
# ──────────────────────────────────────────────────────────────────────────────

def get_leads_for_pipeline(limit: int = 60) -> list:
    """Leads avec email, non envoyés et pas encore approuvés pour envoi."""
    try:
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT lb.id, lb.nom, lb.email, lb.ville, lb.category
                FROM leads_bruts lb
                WHERE lb.email IS NOT NULL AND lb.email != ''
                  AND lb.statut NOT IN ('envoye', 'email_sent')
                  AND lb.id NOT IN (
                      SELECT DISTINCT lead_id FROM emails_envoyes
                      WHERE lead_id IS NOT NULL
                  )
                  AND lb.id NOT IN (
                      SELECT lead_id FROM leads_audites
                      WHERE approuve = 1
                  )
                ORDER BY lb.id DESC
                LIMIT ?
            """, (limit,)).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"[PIPELINE] get_leads_for_pipeline: {e}")
        return []


# ──────────────────────────────────────────────────────────────────────────────
# GÉNÉRATION EMAIL (copywriter SQLite)
# ──────────────────────────────────────────────────────────────────────────────

from envoi.email_tracking_service import EmailTrackingService

def generate_email_for_lead(lead_id: int) -> bool:
    """
    Génère email_objet + email_corps pour un lead via les fonctions pures
    du copywriter, puis sauvegarde dans leads_audites et emails_envoyes.
    """
    try:
        with get_conn() as conn:
            row = conn.execute("""
                SELECT
                    lb.id, lb.nom, lb.email, lb.ville,
                    lb.category, lb.site_web, lb.telephone,
                    lb.rating, lb.nb_avis        AS reviews_count,
                    la.mobile_score, la.desktop_score,
                    la.lcp_ms, la.fcp_ms, la.cls,
                    la.has_https, la.has_meta_description,
                    la.h1_count, la.render_blocking_scripts,
                    la.uses_cache, la.tel_link, la.has_contact_button,
                    la.images_without_alt, la.has_analytics,
                    la.cms_detected, la.score_performance,
                    la.score_seo, la.score_gmb, la.lien_rapport,
                    la.statut AS site_analysee
                FROM leads_bruts lb
                JOIN leads_audites la ON la.lead_id = lb.id
                WHERE lb.id = ?
            """, (lead_id,)).fetchone()

        if not row:
            return False

        audit_dict = dict(row)

        from copywriter.main import (
            get_all_impacts, extract_problemes_detectes,
            determine_main_problem, generate_email_content,
        )

        impacts   = get_all_impacts(audit_dict)
        problemes = extract_problemes_detectes(impacts, audit_dict)
        main_prob = determine_main_problem(problemes, impacts)

        if not main_prob:
            return False

        copy_res  = generate_email_content(audit_dict, main_prob)
        situation = copy_res.get('phrase_synthese', '')

        # Mapper situation → profil email_builder
        situation_to_profile = {
            'Site lent sur mobile':        'B',
            'Bon GMB, mauvais site':       'B',
            'Pas de bouton contact / tel': 'B',
            'CMS vieillot (Wix/Jimdo)':   'B',
            'Pas de meta description':     'D',
            "Peu d'avis Google":           'C',
            'Note Google faible':          'C',
            'Pas de site web':             'A',
        }
        profile = situation_to_profile.get(situation, 'B')
        
        # A/B Testing : Allocation aléatoire 50/50 
        import random
        variant = random.choice(['v1', 'v2'])
        audit_dict['template_variant'] = variant

        # Résoudre l'URL du rapport
        lien = audit_dict.get('lien_rapport') or ''
        if lien.startswith('local://'):
            slug = lien.replace('local://', '').strip('/')
            lien = f'https://audit.incidenx.com/{slug}/'

        # --- MODULE 4: Enrichissement CEO ---
        if not audit_dict.get('prenom_gerant'):
            from enrichisseur.ceo_finder import find_ceo_from_url
            site_web = audit_dict.get('site_web')
            if site_web:
                prenom, nom_ceo = find_ceo_from_url(site_web)
                if prenom:
                    audit_dict['prenom_gerant'] = prenom
                    audit_dict['nom_gerant'] = nom_ceo
                    with get_conn() as conn:
                        conn.execute("UPDATE leads_bruts SET prenom_gerant=?, nom_gerant=? WHERE id= ?", 
                                     (prenom, nom_ceo, lead_id))
                        conn.commit()

        # Générer le HTML via email_builder (vrais templates A/B/C/D)
        sys.path.insert(0, ROOT)
        from envoi.email_builder import build_premium_email
        builder_data = {**audit_dict, 'profile': profile, 'lien_rapport': lien or 'https://incidenx.com'}
        email_corps = build_premium_email(builder_data, verify_link=False)

        if not email_corps:
            return False

        # Extraire le sujet depuis le <title> du template généré
        import re as _re
        title_match = _re.search(r'<title>([^<]+)</title>', email_corps)
        email_objet = title_match.group(1) if title_match else situation

        # Mise à jour leads_audites (inchangé)
        with get_conn() as conn:
            conn.execute("""
                UPDATE leads_audites
                SET email_objet=?, email_corps=?, approuve=0, template_variant=?
                WHERE lead_id=?
            """, (email_objet, email_corps, variant, lead_id))
            conn.commit()

        # Ajout dans emails_envoyes via EmailTrackingService
        tracking_service = EmailTrackingService(db_path=os.getenv('DB_PATH', 'data/prospection.db'))
        tracking_service.create_email_record(
            lead_id=lead_id,
            email=audit_dict.get('email'),
            subject=email_objet,
            body=email_corps,
            lien_rapport=lien,
            approuve=0
        )

        return True

    except Exception as e:
        logger.error(f"[PIPELINE] generate_email_for_lead #{lead_id}: {e}")
        return False


# ──────────────────────────────────────────────────────────────────────────────
# TELEGRAM HELPERS
# ──────────────────────────────────────────────────────────────────────────────

DASHBOARD_URL = "http://127.0.0.1:5001"



def _publish_reports(lead_ids: list) -> dict:
    """
    Publie sur GitHub Pages tous les rapports locaux (local://slug/) du lot.
    Retourne un dict {lead_id: public_url}.
    """
    import shutil
    sys.path.insert(0, os.path.join(ROOT, 'synthetiseur'))
    try:
        from synthetiseur.github_publisher import _commit_files, AUDIT_DOMAIN
    except Exception as e:
        logger.warning(f"[PIPELINE] github_publisher non dispo : {e}")
        return {}

    reports_dir = os.path.join(ROOT, 'reporter', 'reports')
    result = {}

    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT lead_id, lien_rapport FROM leads_audites WHERE lead_id IN ({','.join('?'*len(lead_ids))})",
            lead_ids
        ).fetchall()

    for row in rows:
        lid = row[0]
        lien = row[1] or ""
        if not lien.startswith("local://"):
            if lien.startswith("https://"):
                result[lid] = lien
            continue

        slug = lien.replace("local://", "").strip("/")
        slug_dir = os.path.join(reports_dir, slug)
        index_path = os.path.join(slug_dir, 'index.html')

        if not os.path.exists(index_path):
            continue

        files_to_commit = []
        try:
            with open(index_path, 'r', encoding='utf-8', errors='replace') as f:
                files_to_commit.append({'path': f'{slug}/index.html', 'content': f.read(), 'is_binary': False})
            for fname in os.listdir(slug_dir):
                if fname.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    with open(os.path.join(slug_dir, fname), 'rb') as f:
                        files_to_commit.append({'path': f'{slug}/{fname}', 'content': f.read(), 'is_binary': True})

            if _commit_files(files_to_commit, f'Rapport {slug}'):
                public_url = f'https://{AUDIT_DOMAIN}/{slug}/'
                local_url  = f'http://127.0.0.1:5001/previews/{slug}/'
                with get_conn() as conn:
                    conn.execute("UPDATE leads_audites SET lien_rapport=? WHERE lead_id=?", (public_url, lid))
                    # Remplacer l'URL locale dans le corps du mail par l'URL publique
                    conn.execute("""
                        UPDATE leads_audites SET email_corps = REPLACE(REPLACE(email_corps, ?, ?), '[lien rapport]', ?)
                        WHERE lead_id=?
                    """, (local_url, public_url, public_url, lid))
                    conn.commit()
                shutil.rmtree(slug_dir, ignore_errors=True)
                result[lid] = public_url
                logger.info(f"[PIPELINE] Rapport publié : {public_url}")
        except Exception as e:
            logger.warning(f"[PIPELINE] Publish échoué pour {slug}: {e}")

    return result


def _publish_review_page(lead_ids: list, public_urls: dict) -> str:
    """
    Génère la page de review statique et la pousse sur GitHub Pages.
    Retourne l'URL publique (https://audit.incidenx.com/reviews/YYYY-MM-DD/).
    En cas d'échec, retourne l'URL locale Flask.
    """
    try:
        from synthetiseur.github_publisher import _commit_files, AUDIT_DOMAIN
    except Exception:
        ids_str = ",".join(str(i) for i in lead_ids)
        return f"{DASHBOARD_URL}/review?ids={ids_str}"

    today_str = datetime.now().strftime("%Y-%m-%d")
    slug = f"reviews/{today_str}"

    leads = []
    with get_conn() as conn:
        for lid in lead_ids:
            row = conn.execute("""
                SELECT lb.id, lb.nom, lb.email, lb.site_web, lb.rating, lb.nb_avis,
                       la.probleme_principal, la.score_urgence,
                       la.email_objet, la.email_corps, la.lien_rapport
                FROM leads_bruts lb
                JOIN leads_audites la ON lb.id = la.lead_id
                WHERE lb.id = ?
            """, (lid,)).fetchone()
            if row:
                d = dict(row)
                # Préférer l'URL publique si dispo
                d["preview_url"] = public_urls.get(lid) or (
                    d["lien_rapport"] if (d["lien_rapport"] or "").startswith("https://") else None
                )
                leads.append(d)

    total = len(leads)
    rows_html = ""
    for i, l in enumerate(leads, 1):
        rapport_btn = (
            f'<a href="{l["preview_url"]}" target="_blank" class="btn-rapport">Voir rapport</a>'
            if l.get("preview_url") else '<span class="no-rapport">—</span>'
        )
        nom = (l['nom'] or '').replace('<', '&lt;').replace('>', '&gt;')
        email = (l['email'] or '—').replace('<', '&lt;')
        prob = (l['probleme_principal'] or 'Non défini').replace('<', '&lt;')
        sujet = (l['email_objet'] or '—').replace('<', '&lt;')
        corps = (l['email_corps'] or '').replace('</script', '&lt;/script').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        rating_badge = f'<span class="badge rating">⭐ {l["rating"]} ({l["nb_avis"] or 0} avis)</span>' if l.get('rating') else ''
        rows_html += f"""
        <div class="lead-card">
          <div class="lead-header">
            <span class="lead-num">{i}</span>
            <div class="lead-info">
              <strong>{nom}</strong>
              <span class="lead-email">{email}</span>
            </div>
            <div class="lead-scores">
              <span class="badge urgence">⚡ {l['score_urgence'] or '?'}/10</span>
              {rating_badge}
            </div>
            {rapport_btn}
          </div>
          <div class="lead-problem">{prob}</div>
          <div class="email-subject">📧 <em>{sujet}</em></div>
          <details class="email-body">
            <summary>Voir le corps du mail</summary>
            <pre>{corps}</pre>
          </details>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Review Pipeline — {total} leads — {today_str}</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0c2832;color:#d0e8ec;padding:20px}}
    h1{{font-size:1.4rem;margin-bottom:6px;color:#e8f4f7}}
    .subtitle{{color:#6a9aaa;font-size:.85rem;margin-bottom:20px}}
    .lead-card{{background:#0f3040;border:1px solid #1a4a5a;border-radius:10px;padding:14px 16px;margin-bottom:12px}}
    .lead-header{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px}}
    .lead-num{{background:#1a4a5a;color:#7ab8c8;border-radius:50%;width:26px;height:26px;display:flex;align-items:center;justify-content:center;font-size:.75rem;flex-shrink:0}}
    .lead-info{{flex:1}}
    .lead-info strong{{display:block;font-size:.95rem;color:#e8f4f7}}
    .lead-email{{font-size:.78rem;color:#6a9aaa}}
    .lead-scores{{display:flex;gap:6px;flex-wrap:wrap}}
    .badge{{font-size:.72rem;padding:2px 8px;border-radius:20px}}
    .badge.urgence{{background:#3a1a1a;color:#ff8a7a}}
    .badge.rating{{background:#0f3a2a;color:#7adca8}}
    .btn-rapport{{background:#1a5a6a;color:#7ad4e8;border:1px solid #2a7a8a;padding:4px 12px;border-radius:6px;font-size:.78rem;text-decoration:none;white-space:nowrap}}
    .btn-rapport:hover{{background:#2a7a8a}}
    .no-rapport{{color:#3a6a7a;font-size:.78rem}}
    .lead-problem{{font-size:.82rem;color:#f0c060;margin-bottom:6px;padding:4px 8px;background:#1a2a10;border-radius:4px}}
    .email-subject{{font-size:.83rem;color:#8ab8c8;margin-bottom:6px}}
    .email-body summary{{font-size:.78rem;color:#4a8a9a;cursor:pointer;margin-top:4px}}
    .email-body summary:hover{{color:#7ab8c8}}
    .email-body pre{{margin-top:8px;font-size:.78rem;white-space:pre-wrap;color:#a8d0da;background:#081e28;padding:10px;border-radius:6px;border:1px solid #1a4a5a}}
  </style>
</head>
<body>
  <h1>Review Pipeline — {total} leads</h1>
  <p class="subtitle">Validés le {today_str} · Envoi demain 10h + 14h</p>
  {rows_html}
</body>
</html>"""

    try:
        success = _commit_files(
            [{'path': f'{slug}/index.html', 'content': html, 'is_binary': False}],
            f'Review pipeline {today_str}'
        )
        if success:
            public_url = f'https://{AUDIT_DOMAIN}/{slug}/'
            logger.info(f"[PIPELINE] Page review publiée : {public_url}")
            return public_url
    except Exception as e:
        logger.warning(f"[PIPELINE] Review page publish failed: {e}")

    # Fallback local
    ids_str = ",".join(str(i) for i in lead_ids)
    return f"{DASHBOARD_URL}/review?ids={ids_str}"


def _telegram_send(outil: str, preview: str, callback_id: str):
    """Envoie une demande de validation Telegram (non-bloquant)."""
    try:
        from telegram_notifier import send_validation_request
        send_validation_request(outil, preview, callback_id, timeout_minutes=300)
        logger.info(f"[PIPELINE] Telegram envoyé : {outil} (cb={callback_id})")
    except Exception as e:
        logger.error(f"[PIPELINE] Telegram send error: {e}")


def _telegram_wait(callback_id: str, timeout_seconds: int = 18000) -> str:
    """
    Attend la réponse Telegram. Bloquant jusqu'à timeout_seconds secondes.
    Retourne 'ok', 'no' ou 'timeout'.
    Note : check_pending_db(timeout_minutes=X) compare en secondes (bug connu).
    """
    try:
        from telegram_notifier import check_pending_db
        return check_pending_db(callback_id, timeout_minutes=timeout_seconds)
    except Exception as e:
        logger.error(f"[PIPELINE] Telegram wait error: {e}")
        return "timeout"


# ──────────────────────────────────────────────────────────────────────────────
# APPROBATION
# ──────────────────────────────────────────────────────────────────────────────

def _approve_batch(lead_ids: list):
    """Marque approuve=1 dans leads_audites pour les leads du lot."""
    if not lead_ids:
        return
    with get_conn() as conn:
        placeholders = ','.join('?' * len(lead_ids))
        conn.execute(
            f"UPDATE leads_audites SET approuve=1 WHERE lead_id IN ({placeholders})",
            lead_ids
        )
        conn.commit()
    logger.info(f"[PIPELINE] {len(lead_ids)} leads approuvés pour envoi.")


def notify_new_audits():
    """
    Notifie Telegram des nouveaux audits prêts (email généré, en attente d'approbation).
    N'envoie la notification qu'une seule fois par lead.
    Utilise un cooldown de 30 minutes pour éviter les doublons.
    """
    import time
    from telegram_notifier import notify
    
    last_notif = float(_get_setting('last_notif', 0))
    if (time.time() - last_notif) < 1800:
        logger.info("[PIPELINE] Notification ignorée (cooldown de 30min)")
        return
    
    try:
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT la.lead_id, lb.nom, la.email_objet
                FROM leads_audites la
                JOIN leads_bruts lb ON la.lead_id = lb.id
                WHERE la.email_corps IS NOT NULL AND la.email_corps != ''
                  AND la.approuve = 0
                  AND (la.email_objet IS NOT NULL AND la.email_objet != '')
                  AND (la.notified_at IS NULL OR la.notified_at = '')
                ORDER BY la.lead_id DESC
                LIMIT 50
            """).fetchall()
            
            if not rows:
                return
            
            lead_ids = [r['lead_id'] for r in rows]
            placeholders = ','.join('?' * len(lead_ids))
            conn.execute(f"UPDATE leads_audites SET notified_at = datetime('now') WHERE lead_id IN ({placeholders})", lead_ids)
            conn.commit()
            
            msg = f"*Nouveaux audits prêts — {len(lead_ids)} email(s)*\n\n"
            for r in rows[:10]:
                nom = (r['nom'] or '')[:30]
                obj = (r['email_objet'] or '')[:40]
                msg += f"• {nom}\n  _{obj}_\n"
            
            if len(rows) > 10:
                msg += f"\n_...+{len(rows) - 10} autres_"
            
            msg += "\n\n⏰ Ces emails seront auto-approuvés dans 5h si pas de validation."
            
            notify("Audits prêts", msg)
            _set_setting('last_notif', time.time())
            logger.info(f"[PIPELINE] Notification Telegram: {len(lead_ids)} audits prêts")
            
    except Exception as e:
        logger.error(f"[PIPELINE] notify_new_audits: {e}")


def auto_approve_after_timeout():
    """
    Auto-approve les emails non approuvés après 5 heures.
    Appelé toutes les heures par le scheduler.
    """
    import time
    from telegram_notifier import notify
    
    try:
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT la.lead_id
                FROM leads_audites la
                WHERE la.email_corps IS NOT NULL AND la.email_corps != ''
                  AND la.approuve = 0
                  AND (la.email_objet IS NOT NULL AND la.email_objet != '')
                  AND (la.notified_at IS NOT NULL AND la.notified_at != '')
                  AND (datetime(la.notified_at) < datetime('now', '-5 hours'))
            """).fetchall()
            
            if not rows:
                return
            
            lead_ids = [r['lead_id'] for r in rows]
            placeholders = ','.join('?' * len(lead_ids))
            conn.execute(f"UPDATE leads_audites SET approuve=1 WHERE lead_id IN ({placeholders})", lead_ids)
            conn.commit()
            
            logger.info(f"[PIPELINE] Auto-approval: {len(lead_ids)} leads approuvés après 5h")
            
            last_notif = float(_get_setting('last_auto_approve', 0))
            if lead_ids and (time.time() - last_notif) >= 3600:
                notify("Auto-approval", f"{len(lead_ids)} emails ont été auto-approuvés (5h sans validation)")
                _set_setting('last_auto_approve', time.time())
            
    except Exception as e:
        logger.error(f"[PIPELINE] auto_approve_after_timeout: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# PIPELINE PRINCIPAL
# ──────────────────────────────────────────────────────────────────────────────

def run_evening_pipeline():
    """DEPRECATED — remplacé par maintain_batch_slots(). Gardé pour compatibilité scheduler."""
    logger.info("[PIPELINE] run_evening_pipeline() est DEPRECATED — utiliser maintain_batch_slots()")
    maintain_batch_slots()


# ──────────────────────────────────────────────────────────────────────────────
# NOUVEAU PIPELINE — BATCHES PROGRAMMÉS SUR RESEND
# ──────────────────────────────────────────────────────────────────────────────

BATCH_SIZE     = 50   # emails par batch
TARGET_BATCHES = 4    # toujours 4 batches programmés (J 10h, J 14h, J+1 10h, J+1 14h)
SEND_HOURS     = [10, 14]
RESEND_DAILY_LIMIT = 100  # quota journalier Resend (2 batches de 50)


def get_resend_daily_usage() -> int:
    """
    Retourne le nombre d'emails déjà programmés ou envoyés aujourd'hui via Resend.
    Compte les batches pending + sent dont la date de programmation est aujourd'hui.
    """
    try:
        today_str = _now_paris().strftime('%Y-%m-%d')
        with get_conn() as conn:
            # Batches pending aujourd'hui
            r1 = conn.execute("""
                SELECT COALESCE(SUM(nb_emails), 0) as total FROM scheduled_batches
                WHERE status = 'pending' AND DATE(scheduled_at) = ?
            """, (today_str,)).fetchone()
            pending_today = r1['total'] if r1 else 0
            
            # Batches sent aujourd'hui
            r2 = conn.execute("""
                SELECT COALESCE(SUM(nb_emails), 0) as total FROM scheduled_batches
                WHERE status = 'sent' AND DATE(scheduled_at) = ?
            """, (today_str,)).fetchone()
            sent_today = r2['total'] if r2 else 0
            
            # Batches queued aujourd'hui (en attente locale) ne consomment pas de quota Resend
            return pending_today + sent_today
    except Exception as e:
        logger.error(f"[FILL] get_resend_daily_usage: {e}")
        return 0


def get_total_resend_quota() -> int:
    """Calcule le quota global basé sur le nombre de comptes actifs."""
    try:
        with get_conn() as conn:
            r = conn.execute("SELECT COUNT(*) as n FROM resend_accounts WHERE actif = 1").fetchone()
            return r['n'] * 100 if r else RESEND_DAILY_LIMIT
    except:
        return RESEND_DAILY_LIMIT


def get_resend_quota_remaining() -> int:
    """Retourne le quota Resend restant aujourd'hui."""
    return max(0, get_total_resend_quota() - get_resend_daily_usage())


def get_future_pending_batches() -> int:
    """Retourne le nombre de batches pending (sur Resend) avec heure future."""
    try:
        now_str = _now_paris().isoformat()
        with get_conn() as conn:
            r = conn.execute("""
                SELECT COUNT(*) as n FROM scheduled_batches
                WHERE status = 'pending' AND scheduled_at > ?
            """, (now_str,)).fetchone()
        return r['n'] if r else 0
    except Exception as e:
        logger.error(f"[FILL] get_future_pending_batches: {e}")
        return 0


def get_future_queued_batches() -> int:
    """Retourne le nombre de batches queued (en attente locale) avec heure future."""
    try:
        now_str = _now_paris().isoformat()
        with get_conn() as conn:
            r = conn.execute("""
                SELECT COUNT(*) as n FROM scheduled_batches
                WHERE status = 'queued' AND scheduled_at > ?
            """, (now_str,)).fetchone()
        return r['n'] if r else 0
    except Exception as e:
        logger.error(f"[FILL] get_future_queued_batches: {e}")
        return 0


def _now_paris() -> datetime:
    try:
        return datetime.now(TZ)
    except Exception:
        return datetime.now()


def reconcile_batches():
    """Marque 'sent' les batches dont l'heure programmée est passée, et notifie Telegram."""
    try:
        now_str = _now_paris().isoformat()
        with get_conn() as conn:
            # Récupérer les batches qui vont être marqués sent pour les notifier
            just_sent = conn.execute("""
                SELECT batch_key, scheduled_at, nb_emails FROM scheduled_batches
                WHERE status='pending' AND scheduled_at <= ?
            """, (now_str,)).fetchall()

            if just_sent:
                conn.execute("""
                    UPDATE scheduled_batches SET status='sent'
                    WHERE status='pending' AND scheduled_at <= ?
                """, (now_str,))
                conn.commit()

        for batch in just_sent:
            logger.info(f"[FILL] Batch {batch['batch_key']} marqué 'sent' ({batch['nb_emails']} emails)")
            _notify_batch_sent(batch['batch_key'], batch['scheduled_at'], batch['nb_emails'])

    except Exception as e:
        logger.error(f"[FILL] reconcile_batches: {e}")


def _notify_batch_sent(batch_key: str, scheduled_at: str, nb_emails: int):
    """Envoie une notification Telegram confirmant qu'un batch a été envoyé."""
    def _bg():
        try:
            from telegram_notifier import notify
            try:
                from datetime import datetime as _dt
                slot = _dt.fromisoformat(scheduled_at)
                slot_fr = slot.strftime("%A %d/%m à %Hh").capitalize()
            except Exception:
                slot_fr = scheduled_at

            msg = (
                f"*{nb_emails} emails envoyés — {slot_fr}*\n\n"
                f"Batch `{batch_key}` expédié par Resend ✅\n"
                f"Résultats disponibles dans le dashboard."
            )
            notify(f"Envoi {slot_fr}", msg)
        except Exception as e:
            logger.error(f"[FILL] _notify_batch_sent: {e}")

    threading.Thread(target=_bg, daemon=True).start()


def count_future_batches() -> int:
    """Nombre de batches en statut 'pending' ou 'queued' avec heure future."""
    try:
        now_str = _now_paris().isoformat()
        with get_conn() as conn:
            r = conn.execute("""
                SELECT COUNT(*) as n FROM scheduled_batches
                WHERE status IN ('pending', 'queued') AND scheduled_at > ?
            """, (now_str,)).fetchone()
        return r['n'] if r else 0
    except Exception as e:
        logger.error(f"[FILL] count_future_batches: {e}")
        return 0


def get_next_available_slot() -> datetime:
    """
    Retourne le prochain créneau libre (10h ou 14h) non encore occupé par un batch.
    Inclut pending, queued mais ignore cancelled.
    """
    now = _now_paris()
    
    with get_conn() as conn:
        rows = conn.execute("SELECT scheduled_at FROM scheduled_batches WHERE status != 'cancelled'").fetchall()
        taken = {r['scheduled_at'][:16] for r in rows}

    d = now.date()
    if now.hour >= 14:
        d += timedelta(days=1)

    for _ in range(30):
        for hour in [10, 14]:
            try:
                slot = TZ.localize(datetime(d.year, d.month, d.day, hour, 0, 0))
            except Exception:
                slot = datetime(d.year, d.month, d.day, hour, 0, 0)
            if slot <= now:
                continue
            
            slot_key = slot.isoformat()[:16]
            if slot_key not in taken:
                return slot
        d += timedelta(days=1)
    return None


def _get_leads_for_batch() -> list:
    """
    Retourne jusqu'à BATCH_SIZE leads avec email, non déjà dans un batch pending/sent/scheduled.
    """
    try:
        with get_conn() as conn:
            # Récupérer les lead_ids déjà dans des batches pending ou queued
            rows = conn.execute(
                "SELECT lead_ids FROM scheduled_batches WHERE status IN ('pending', 'queued')"
            ).fetchall()
            already_scheduled = set()
            for row in rows:
                if row['lead_ids']:
                    already_scheduled.update(json.loads(row['lead_ids']))

            candidates = conn.execute("""
                SELECT lb.id, lb.nom, lb.email, lb.ville, lb.category
                FROM leads_bruts lb
                JOIN leads_audites la ON la.lead_id = lb.id
                WHERE lb.email IS NOT NULL AND lb.email != ''
                  AND (lb.email_valide = 'Valide' OR lb.email_valide IS NULL)
                  AND lb.statut NOT IN ('envoye', 'email_sent', 'scheduled')
                  AND la.approuve = 1
                  AND la.email_corps IS NOT NULL AND la.email_corps != ''
                  AND lb.id NOT IN (
                      SELECT DISTINCT lead_id FROM emails_envoyes WHERE lead_id IS NOT NULL
                  )
                ORDER BY la.score_urgence DESC, lb.id DESC
                LIMIT ?
            """, (BATCH_SIZE * 4,)).fetchall()

        result = []
        for r in candidates:
            if r['id'] not in already_scheduled:
                result.append(dict(r))
            if len(result) >= BATCH_SIZE:
                break
        return result
    except Exception as e:
        logger.error(f"[FILL] _get_leads_for_batch: {e}")
        return []


def _run_scraping_sync(min_emails: int):
    """Lance le scraper et attend qu'il termine (bloquant, max 90 min)."""
    try:
        sys.path.insert(0, os.path.join(ROOT, 'dashboard'))
        from auto_planner import get_next_priorities
        from datetime import date as dt_date

        today = dt_date.today().isoformat()
        candidates = get_next_priorities(1, today)
        if not candidates:
            logger.warning("[FILL] Aucune priorité de scraping disponible")
            return

        c = candidates[0]
        logger.info(f"[FILL] Scraping: {c['keyword']} {c['ville']} — objectif {min_emails} emails")

        cmd = [
            sys.executable,
            os.path.join(ROOT, 'scraper', 'main.py'),
            '--keyword', c['keyword'],
            '--city', c['ville'],
            '--min-emails', str(min_emails),
            '--limit', str(min_emails * 4),
        ]
        subprocess.run(cmd, cwd=ROOT, timeout=5400)  # max 90 min

        with get_conn() as conn:
            conn.execute(
                "UPDATE scraping_priorities SET derniere_execution=? WHERE id=?",
                (today, c['id'])
            )
            conn.commit()
    except Exception as e:
        logger.error(f"[FILL] _run_scraping_sync: {e}")


def _run_scraping_async(min_emails: int):
    """Lance le scraper dans un thread séparé (non bloquant)."""
    def _scrape():
        try:
            _run_scraping_sync(min_emails)
        except Exception as e:
            logger.error(f"[FILL] _run_scraping_async thread: {e}")
    
    threading.Thread(target=_scrape, daemon=True).start()


def get_available_leads_count() -> int:
    """Retourne le nombre de leads avec email disponibles pour les batches."""
    try:
        with get_conn() as conn:
            # Leads avec email, non dans un batch, non envoyés
            rows = conn.execute("""
                SELECT COUNT(*) as n FROM leads_bruts lb
                WHERE lb.email IS NOT NULL AND lb.email != ''
                  AND lb.statut NOT IN ('envoye', 'email_sent', 'scheduled')
                  AND lb.id NOT IN (
                      SELECT DISTINCT lead_id FROM emails_envoyes WHERE lead_id IS NOT NULL
                  )
                  AND lb.id NOT IN (
                      SELECT lead_id FROM leads_audites WHERE approuve = 1
                  )
            """).fetchone()
            return rows['n'] if rows else 0
    except Exception as e:
        logger.error(f"[FILL] get_available_leads_count: {e}")
        return 0


def background_scraper_loop():
    """
    Boucle de scraping en arrière-plan.
    Vérifie toutes les heures si le nombre de leads disponibles est suffisant.
    Si < BATCH_SIZE * 2 (100), lance le scraping.
    """
    import time
    
    while True:
        try:
            available = get_available_leads_count()
            logger.info(f"[FILL] Background scraper: {available} leads disponibles")
            
            # Si moins de 100 leads disponibles, lancer le scraping
            if available < BATCH_SIZE * 2:
                # Calculer combien d'emails supplémentaires sont nécessaires
                needed = (BATCH_SIZE * 4) - available  # Objectif: avoir assez pour 4 batches
                if needed > 0:
                    logger.info(f"[FILL] Background scraper: lancement scraping pour {needed} emails supplémentaires")
                    _run_scraping_async(needed)
            
            # Attendre 1 heure avant la prochaine vérification
            time.sleep(3600)
            
        except Exception as e:
            logger.error(f"[FILL] background_scraper_loop: {e}")
            time.sleep(300)  # En cas d'erreur, attendre 5 minutes


def start_background_scraper():
    """Démarre le thread de scraping en arrière-plan."""
    import threading
    thread = threading.Thread(target=background_scraper_loop, daemon=True)
    thread.start()
    logger.info("[FILL] Background scraper thread started")


def _notify_and_watch_batch(batch_key: str, slot: datetime, nb: int, lead_ids: list):
    """
    Envoie une notification Telegram pour le batch (fire-and-forget).
    Le batch s'exécute automatiquement sur Resend à l'heure prévue.
    Pour annuler : tapper ❌ dans Telegram ou envoyer /annuler <batch_key> au bot.
    """
    def _bg():
        try:
            slot_fr = slot.strftime("%A %d/%m à %Hh").capitalize()
            preview_lines = []
            with get_conn() as conn:
                for lid in lead_ids[:6]:
                    row = conn.execute("""
                        SELECT lb.nom, la.email_objet FROM leads_bruts lb
                        JOIN leads_audites la ON la.lead_id = lb.id
                        WHERE lb.id = ?
                    """, (lid,)).fetchone()
                    if row:
                        nom = (row['nom'] or '')[:25]
                        obj = (row['email_objet'] or '')[:45]
                        preview_lines.append(f"• {nom} — {obj}")

            more = nb - len(preview_lines)
            msg = (
                f"*{nb} emails programmés — {slot_fr}*\n\n"
                + "\n".join(preview_lines)
                + (f"\n_...+{more} autres_" if more > 0 else "")
                + "\n\n✅ = envoi automatique à l'heure prévue"
                + "\n❌ = annuler ce batch (ou /annuler " + batch_key + ")"
            )

            cb = f"b_{batch_key}"
            _telegram_send(f"Batch {slot_fr}", msg, cb)

        except Exception as e:
            logger.error(f"[FILL] _notify_and_watch_batch {batch_key}: {e}")

    threading.Thread(target=_bg, daemon=True).start()


def fill_incomplete_batches():
    """
    Complète les batches pending dont nb_emails < BATCH_SIZE (50).
    Tente de programmer les leads manquants sur Resend pour le même créneau.
    Garantit que chaque batch atteint exactement BATCH_SIZE emails.
    """
    try:
        now_str = _now_paris().isoformat()
        with get_conn() as conn:
            batches = conn.execute("""
                SELECT batch_key, scheduled_at, lead_ids, message_ids, nb_emails
                FROM scheduled_batches
                WHERE status='pending' AND nb_emails < ? AND scheduled_at > ?
            """, (BATCH_SIZE, now_str)).fetchall()

        if not batches:
            return

        from envoi.resend_sender import schedule_email_batch

        for batch in batches:
            all_lead_ids = json.loads(batch['lead_ids']) if batch['lead_ids'] else []
            existing_msg_ids = json.loads(batch['message_ids']) if batch['message_ids'] else []
            deficit = BATCH_SIZE - batch['nb_emails']

            logger.info(f"[FILL] Batch incomplet {batch['batch_key']}: {batch['nb_emails']}/{BATCH_SIZE} — tentative de complétion (+{deficit})")

            # Retry les leads du batch non encore schedulés (schedule_email_batch skipera les déjà dans emails_envoyes)
            to_schedule = list(all_lead_ids)

            # Si la liste du batch ne suffit pas, piocher des leads supplémentaires
            if len(to_schedule) < deficit:
                extra = _get_leads_for_batch()
                extra_ids = [l['id'] for l in extra if l['id'] not in set(all_lead_ids)]
                to_schedule = to_schedule + extra_ids

            try:
                slot = datetime.fromisoformat(batch['scheduled_at'])
                if hasattr(TZ, 'localize') and slot.tzinfo is None:
                    slot = TZ.localize(slot)
            except Exception:
                continue

            new_msg_ids = schedule_email_batch(to_schedule, slot)

            if new_msg_ids:
                all_msg_ids = existing_msg_ids + new_msg_ids
                new_total = len(all_msg_ids)
                # Mise à jour lead_ids pour inclure les éventuels nouveaux leads
                updated_lead_ids = all_lead_ids + [lid for lid in to_schedule if lid not in set(all_lead_ids)]
                with get_conn() as conn:
                    conn.execute("""
                        UPDATE scheduled_batches
                        SET nb_emails=?, message_ids=?, lead_ids=?
                        WHERE batch_key=?
                    """, (new_total, json.dumps(all_msg_ids),
                          json.dumps(updated_lead_ids), batch['batch_key']))
                    conn.commit()
                logger.info(f"[FILL] Batch {batch['batch_key']} : {batch['nb_emails']} → {new_total}/{BATCH_SIZE}")
            else:
                logger.warning(f"[FILL] Batch {batch['batch_key']} : quota Resend épuisé, retry à la prochaine heure.")
                break  # Quota plein → pas la peine de continuer

    except Exception as e:
        logger.error(f"[FILL] fill_incomplete_batches: {e}")


def push_queued_batches():
    """
    Pousse un seul batch 'queued' sur Resend quand un slot pending se libère et quota disponible.
    Appelé à chaque heure par le scheduler.
    """
    try:
        # Vérifier le quota restant aujourd'hui
        quota_remaining = get_resend_quota_remaining()
        if quota_remaining < BATCH_SIZE:
            logger.info(f"[FILL] push_queued: quota Resend insuffisant ({quota_remaining} restants, besoin de {BATCH_SIZE})")
            return

        # Vérifier combien de batches pending futurs (ne doit pas dépasser 2)
        future_pending = get_future_pending_batches()
        if future_pending >= 2:
            logger.info(f"[FILL] push_queued: déjà {future_pending} batches pending — pas de poussée")
            return

        # Prendre le plus ancien batch queued
        with get_conn() as conn:
            batch = conn.execute("""
                SELECT batch_key, scheduled_at, lead_ids FROM scheduled_batches
                WHERE status='queued' ORDER BY scheduled_at LIMIT 1
            """).fetchone()

        if not batch:
            return

        lead_ids = json.loads(batch['lead_ids']) if batch['lead_ids'] else []
        if not lead_ids:
            return

        try:
            slot = datetime.fromisoformat(batch['scheduled_at'])
            if hasattr(TZ, 'localize') and slot.tzinfo is None:
                slot = TZ.localize(slot)
        except Exception:
            return

        from envoi.resend_sender import schedule_email_batch
        message_ids = schedule_email_batch(lead_ids, slot)
        if not message_ids:
            logger.info(f"[FILL] push_queued: échec de programmation sur Resend")
            return

        # Mettre à jour le batch en pending
        with get_conn() as conn:
            conn.execute("""
                UPDATE scheduled_batches
                SET status='pending', nb_emails=?, message_ids=?
                WHERE batch_key=?
            """, (len(message_ids), json.dumps(message_ids), batch['batch_key']))
            conn.commit()

        logger.info(f"[FILL] Batch queued {batch['batch_key']} → pending ({len(message_ids)} emails sur Resend)")
        _notify_and_watch_batch(batch['batch_key'], slot, len(message_ids), lead_ids)

    except Exception as e:
        logger.error(f"[FILL] push_queued_batches: {e}")


def run_fill_pipeline(_depth: int = 0):
    """DEPRECATED — remplacé par maintain_batch_slots()."""
    logger.info("[PIPELINE] run_fill_pipeline() est DEPRECATED — utiliser maintain_batch_slots()")
    maintain_batch_slots()


def maintain_batch_slots():
    """
    Pipeline principal amélioré.
    Maintient exactement 2 batches pending (sur Resend) et 2 batches queued (en attente locale).
    Quand un batch pending est envoyé, le système crée un nouveau batch en queued.
    Quand un slot pending se libère (après reconcile), pousse un batch queued vers pending.
    """
    from datetime import datetime
    
    lock_time = _get_setting('batch_lock')
    if lock_time:
        if (datetime.now() - datetime.fromisoformat(lock_time)).seconds < 900:
            return 

    _set_setting('batch_lock', datetime.now().isoformat())

    try:
        reconcile_batches()
        
        future_pending = get_future_pending_batches()
        future_queued = get_future_queued_batches()
        total_future = future_pending + future_queued
        
        logger.info(f"[FILL] Maintain: pending={future_pending}, queued={future_queued}, total={total_future}/4")
        
        # Cas 1 : Trop de batches (au-delà de 4) - supprimer les plus lointains
        if total_future > TARGET_BATCHES:
            excess = total_future - TARGET_BATCHES
            logger.warning(f"[FILL] {excess} batch(es) en trop - suppression des plus lointains")
            # TODO: implémenter suppression des batches les plus lointains
            return
        
        # Cas 2 : Manque de batches - en créer
        if total_future < TARGET_BATCHES:
            needed = TARGET_BATCHES - total_future
            logger.info(f"[FILL] {needed} batch(es) manquants - création")
            
            for _ in range(needed):
                # Déterminer si on crée pending ou queued
                # Priorité : compléter pending d'abord, puis queued
                if future_pending < 2:
                    # Créer un batch pending
                    batch = create_batch(pending=True)
                    if batch:
                        future_pending += 1
                else:
                    # Créer un batch queued
                    batch = create_batch(pending=False)
                    if batch:
                        future_queued += 1
                
                if not batch:
                    logger.warning("[FILL] Impossible de créer un batch - arrêt")
                    break
        
        # Cas 3 : Pousser un queued vers pending si un slot pending se libère
        if future_pending < 2 and future_queued > 0:
            push_queued_batches()
            
    except Exception as e:
        logger.error(f"[FILL] maintain_batch_slots: {e}")
    finally:
        with get_conn() as conn:
            conn.execute("DELETE FROM planning_settings WHERE key='batch_lock'")
            conn.commit()


def create_batch(pending: bool = True) -> dict:
    """
    Crée un batch de 50 emails.
    Si pending=True, programme sur Resend (si quota suffisant).
    Si pending=False, crée en statut 'queued' (en attente locale).
    Retourne le batch créé ou None en cas d'erreur.
    """
    try:
        # Vérifier le quota si pending
        if pending:
            quota_remaining = get_resend_quota_remaining()
            if quota_remaining < BATCH_SIZE:
                logger.warning(f"[FILL] create_batch(pending=True): quota insuffisant ({quota_remaining} restants)")
                return None
        
        # Obtenir exactement BATCH_SIZE leads
        leads = _get_leads_for_batch()
        
        if len(leads) < BATCH_SIZE:
            missing = BATCH_SIZE - len(leads)
            logger.info(f"[FILL] Seulement {len(leads)} leads - scraping {missing + 20} emails...")
            _run_scraping_sync(missing + 20)
            leads = _get_leads_for_batch()
        
        if len(leads) < BATCH_SIZE:
            logger.warning(f"[FILL] Impossible d'obtenir {BATCH_SIZE} leads - seulement {len(leads)}")
            return None
        
        batch_leads = leads[:BATCH_SIZE]
        lead_ids = [l['id'] for l in batch_leads]

        # Vérification : tous les leads doivent avoir un email généré et être approuvés
        # (garanti par _get_leads_for_batch() corrigé ci-dessus)
        # Double-check : filtrer les leads sans email_corps
        valid_ids = []
        with get_conn() as conn:
            for lid in lead_ids:
                row = conn.execute("""
                    SELECT email_corps FROM leads_audites
                    WHERE lead_id = ? AND email_corps IS NOT NULL AND email_corps != ''
                      AND approuve = 1
                """, (lid,)).fetchone()
                if row:
                    valid_ids.append(lid)
                else:
                    logger.warning(f"[FILL] Lead #{lid} sans email_corps ou non approuvé — exclu du batch")

        if len(valid_ids) < BATCH_SIZE:
            logger.warning(f"[FILL] Seulement {len(valid_ids)}/{BATCH_SIZE} leads valides après vérification")

        if not valid_ids:
            logger.warning("[FILL] Aucun lead valide pour ce batch — abandon")
            return None

        lead_ids = valid_ids
        
        # Prochain slot disponible
        slot = get_next_available_slot()
        if not slot:
            logger.error("[FILL] Aucun créneau disponible")
            return None
        
        batch_key = slot.strftime("%Y-%m-%d_%Hh")
        
        if pending:
            # Programmer sur Resend
            from envoi.resend_sender import schedule_email_batch
            message_ids = schedule_email_batch(lead_ids, slot)
            
            if not message_ids:
                logger.warning(f"[FILL] create_batch: échec de programmation sur Resend")
                return None
            
            # Sauvegarder en pending
            with get_conn() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO scheduled_batches
                        (batch_key, scheduled_at, status, nb_emails, lead_ids, message_ids)
                    VALUES (?, ?, 'pending', ?, ?, ?)
                """, (batch_key, slot.isoformat(), len(message_ids),
                      json.dumps(lead_ids), json.dumps(message_ids)))
                conn.commit()
            
            logger.info(f"[FILL] Batch pending créé: {batch_key} ({len(message_ids)} emails)")
            _notify_and_watch_batch(batch_key, slot, len(message_ids), lead_ids)
            
        else:
            # Créer en queued (en attente locale)
            with get_conn() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO scheduled_batches
                        (batch_key, scheduled_at, status, nb_emails, lead_ids, message_ids)
                    VALUES (?, ?, 'queued', ?, ?, '[]')
                """, (batch_key, slot.isoformat(), BATCH_SIZE, json.dumps(lead_ids)))
                conn.commit()
            
            logger.info(f"[FILL] Batch queued créé: {batch_key} ({BATCH_SIZE} emails en attente locale)")
            # Pas de notification Telegram pour les batches queued (ils seront notifiés quand poussés vers pending)
        
        return {
            'batch_key': batch_key,
            'scheduled_at': slot.isoformat(),
            'status': 'pending' if pending else 'queued',
            'nb_emails': len(message_ids) if pending else BATCH_SIZE,
            'lead_ids': lead_ids
        }
        
    except Exception as e:
        logger.error(f"[FILL] create_batch: {e}")
        return None
