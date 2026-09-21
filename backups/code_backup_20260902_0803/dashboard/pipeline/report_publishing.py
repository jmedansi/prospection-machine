# -*- coding: utf-8 -*-
"""
dashboard/pipeline/report_publishing.py
Logique de publication des rapports sur GitHub Pages et génération de la page de revue.
"""
import os
import logging
import shutil
from datetime import datetime
from database.db_manager import get_conn

logger = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DASHBOARD_URL = "http://127.0.0.1:5001"

def _verify_url_accessible(url: str, timeout: int = 10) -> bool:
    """Vérifie qu'une URL renvoie HTTP 200."""
    try:
        import requests
        resp = requests.head(url, timeout=timeout, allow_redirects=True)
        return resp.status_code == 200
    except Exception:
        return False


def _publish_reports(lead_ids: list) -> dict:
    """
    Publie sur GitHub Pages tous les rapports locaux (local://slug/) du lot.
    Retourne un dict {lead_id: public_url}.
    """
    try:
        from synthetiseur.github_publisher import _commit_files, AUDIT_DOMAIN
    except Exception as e:
        logger.warning(f"[PIPELINE-Publish] github_publisher non dispo : {e}")
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
            logger.warning(f"[PIPELINE-Publish] Fichier introuvable pour {slug}: {index_path}")
            continue

        files_to_commit = []
        try:
            with open(index_path, 'r', encoding='utf-8', errors='replace') as f:
                files_to_commit.append({'path': f'{slug}/index.html', 'content': f.read(), 'is_binary': False})
            for fname in os.listdir(slug_dir):
                if fname.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    with open(os.path.join(slug_dir, fname), 'rb') as f:
                        files_to_commit.append({'path': f'{slug}/{fname}', 'content': f.read(), 'is_binary': True})

            if not _commit_files(files_to_commit, f'Rapport {slug}'):
                logger.error(f"[PIPELINE-Publish] _commit_files échoué pour {slug} — fichiers locaux conservés")
                continue

            public_url = f'https://{AUDIT_DOMAIN}/{slug}/'

            # Fix 3 : Vérification post-publication
            if not _verify_url_accessible(public_url):
                logger.error(f"[PIPELINE-Publish] Vérification post-publish échouée (404) pour {public_url} — fichiers locaux conservés")
                continue

            # Fix 2 : Corriger le remplacement email_corps (local:// au lieu de http://127.0.0.1)
            local_pattern = f"local://{slug}/"
            with get_conn() as conn:
                conn.execute("UPDATE leads_audites SET lien_rapport=? WHERE lead_id=?", (public_url, lid))
                conn.execute("""
                    UPDATE leads_audites SET email_corps = REPLACE(REPLACE(email_corps, ?, ?), '[lien rapport]', ?)
                    WHERE lead_id=?
                """, (local_pattern, public_url, public_url, lid))
                conn.commit()

            # Fix 2 : Régénérer l'email avec le lien public
            try:
                from services.email_generator import generate_email_for_lead
                generate_email_for_lead(lid)
                logger.info(f"[PIPELINE-Publish] Email régénéré pour lead {lid}")
            except Exception as e:
                logger.warning(f"[PIPELINE-Publish] Régénération email échouée pour lead {lid}: {e}")

            # Fix 4 : Supprimer les fichiers locaux uniquement après succès confirmé
            shutil.rmtree(slug_dir, ignore_errors=True)
            result[lid] = public_url
            logger.info(f"[PIPELINE-Publish] Rapport publié et vérifié : {public_url}")
        except Exception as e:
            logger.warning(f"[PIPELINE-Publish] Publish échoué pour {slug}: {e}")

    return result


def publish_reports_batch(slugs: list) -> str:
    """
    Publie un ou plusieurs rapports locaux sur GitHub Pages.
    Args: slugs — liste de noms de dossiers dans reporter/reports/
    Returns: URL publique du premier rapport publié, ou None.
    """
    try:
        from synthetiseur.github_publisher import _commit_files, AUDIT_DOMAIN
    except Exception as e:
        logger.warning(f"[PIPELINE-Publish] github_publisher non dispo : {e}")
        return None

    reports_dir = os.path.join(ROOT, 'reporter', 'reports')

    for slug in slugs:
        slug_dir = os.path.join(reports_dir, slug)
        index_path = os.path.join(slug_dir, 'index.html')

        if not os.path.isdir(slug_dir) or not os.path.isfile(index_path):
            logger.warning(f"[PIPELINE-Publish] Dossier ou index.html manquant pour {slug}")
            continue

        files_to_commit = []
        try:
            with open(index_path, 'r', encoding='utf-8', errors='replace') as f:
                files_to_commit.append({'path': f'{slug}/index.html', 'content': f.read(), 'is_binary': False})
            for fname in os.listdir(slug_dir):
                if fname.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    with open(os.path.join(slug_dir, fname), 'rb') as f:
                        files_to_commit.append({'path': f'{slug}/{fname}', 'content': f.read(), 'is_binary': True})

            if not _commit_files(files_to_commit, f'Rapport {slug}'):
                logger.error(f"[PIPELINE-Publish] _commit_files échoué pour {slug} — fichiers locaux conservés")
                continue

            public_url = f'https://{AUDIT_DOMAIN}/{slug}/'

            # Fix 3 : Vérification post-publication
            if not _verify_url_accessible(public_url):
                logger.error(f"[PIPELINE-Publish] Vérification post-publish échouée (404) pour {public_url} — fichiers locaux conservés")
                continue

            # Fix 2 : Régénérer l'email avec le lien public AVANT de supprimer les fichiers locaux
            local_pattern = f"local://{slug}/"
            lead_id = None
            with get_conn() as conn:
                row = conn.execute(
                    "SELECT lead_id FROM leads_audites WHERE lien_rapport LIKE ?",
                    (f"local://{slug}%",)
                ).fetchone()
                if row:
                    lead_id = row[0]
                    conn.execute("UPDATE leads_audites SET lien_rapport=? WHERE lead_id=?", (public_url, lead_id))
                    conn.execute("""
                        UPDATE leads_audites SET email_corps = REPLACE(REPLACE(email_corps, ?, ?), '[lien rapport]', ?)
                        WHERE lead_id=?
                    """, (local_pattern, public_url, public_url, lead_id))
                    conn.commit()

            if lead_id:
                try:
                    from services.email_generator import generate_email_for_lead
                    generate_email_for_lead(lead_id)
                    logger.info(f"[PIPELINE-Publish] Email régénéré pour lead {lead_id}")
                except Exception as e:
                    logger.warning(f"[PIPELINE-Publish] Régénération email échouée pour lead {lead_id}: {e}")

            # Fix 4 : Supprimer les fichiers locaux uniquement après succès confirmé
            shutil.rmtree(slug_dir, ignore_errors=True)
            logger.info(f"[PIPELINE-Publish] Rapport publié et vérifié : {public_url}")
            return public_url
        except Exception as e:
            logger.warning(f"[PIPELINE-Publish] Publish échoué pour {slug}: {e}")

    return None


def _publish_review_page(lead_ids: list, public_urls: dict) -> str:
    """
    Génère la page de review statique et la pousse sur GitHub Pages.
    Retourne l'URL publique ou l'URL locale Flask en cas d'échec.
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
            logger.info(f"[PIPELINE-Publish] Page review publiée : {public_url}")
            return public_url
    except Exception as e:
        logger.warning(f"[PIPELINE-Publish] Review page publish failed: {e}")

    ids_str = ",".join(str(i) for i in lead_ids)
    return f"{DASHBOARD_URL}/review?ids={ids_str}"
