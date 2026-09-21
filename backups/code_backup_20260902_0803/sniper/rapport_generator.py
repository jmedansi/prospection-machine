# -*- coding: utf-8 -*-
"""
sniper/rapport_generator.py — Génération et publication du rapport d'audit Sniper

Lire sniper/README.md avant toute modification.

Prend les données brutes d'un lead Sniper (donnees_audit JSON) et génère
une page HTML professionnelle publiée sur audit.incidenx.com/{slug}/.

Réutilise synthetiseur/github_publisher.push_audit_to_github() — même infra
que le pipeline Maps, pas de duplication.

Usage :
    from sniper.rapport_generator import generate_and_publish
    url = generate_and_publish(lead_id=42)
    # → "https://audit.incidenx.com/dupont-solar-fr/"
"""

import json
import logging
import os
import re
import sys
import time
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

logger = logging.getLogger(__name__)


from core.scoring import score_label as _score_label, score_color as _score_color
from core.scoring import lcp_label as _lcp_label, lcp_color as _lcp_color
from core.audit_data import parse_donnees_audit as _parse_audit

def _bool_badge(val, label_true: str, label_false: str, color_true="#10b981", color_false="#ef4444") -> str:
    if val:
        return f'<span style="background:{color_true}20;color:{color_true};padding:3px 10px;border-radius:12px;font-size:12px;font-weight:700">{label_true}</span>'
    return f'<span style="background:{color_false}20;color:{color_false};padding:3px 10px;border-radius:12px;font-size:12px;font-weight:700">{label_false}</span>'


# ─── Génération HTML ──────────────────────────────────────────────────────────

def generate_sniper_rapport_html(lead: dict, donnees: dict) -> str:
    """
    Génère le HTML complet du rapport Sniper via rapport-profil-b-technique.html.

    Args:
        lead:    Dict avec nom, site_web, ceo_prenom, ceo_nom, tag_urgence, etc.
        donnees: Dict parsé depuis leads_audites.donnees_audit (JSON)
    """
    d = _parse_audit(donnees)

    try:
        from jinja2 import Environment, FileSystemLoader
        from reporter.main import enrich_data

        audit_data = {
            "nom":                  lead.get("nom") or lead.get("site_web", ""),
            "site_web":             lead.get("site_web", ""),
            "ville":                lead.get("ville", ""),
            "category":             lead.get("category", ""),
            "mobile_score":         d["score_mobile"],
            "desktop_score":        d["score_desktop"],
            "lcp_ms":               d["lcp_ms"] or 3000,
            "fcp_ms":               d["fcp_ms"],
            "rating":               0,
            "reviews_count":        0,
            "template_used":        "audit",
            "has_site":             True,
            "score_priorite":       lead.get("score_urgence"),
            "has_https":            d["has_https"],
            "has_meta_description": bool(donnees.get("has_meta")),
            "screenshot_desktop":   "",
            "screenshot_mobile":    "",
        }
        enriched = enrich_data(audit_data)

        template_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "templates", "rapports",
        )
        env = Environment(loader=FileSystemLoader(template_dir))
        return env.get_template("rapport-profil-b-technique.html").render(**enriched)

    except Exception as e:
        logger.warning(f"rapport_generator: fallback HTML inline — {e}")

    # ── Fallback : HTML inline minimal ────────────────────────────────────────
    nom_entreprise = lead.get("nom") or lead.get("site_web", "")
    tag            = lead.get("tag_urgence") or donnees.get("tag", "perf")
    date_audit     = time.strftime("%d/%m/%Y")
    calendly       = os.getenv("CALENDLY_URL", "https://calendly.com/jmedansi")

    # Métriques performance
    score_mobile = d["score_mobile"]
    lcp_ms       = d["lcp_ms"]
    fcp_ms       = d["fcp_ms"]
    blocking     = d["render_blocking_scripts"]
    page_kb      = d["page_size_kb"]

    # Infrastructure
    cms        = d["cms"] or "Non détecté"
    server     = d["server"] or "Non détecté"
    has_cdn    = d["has_cdn"]
    has_https  = d["has_https"]
    has_waf    = d["has_waf"]
    reason     = d["reason"]

    score_color = _score_color(score_mobile)
    score_lbl   = _score_label(score_mobile)
    lcp_color   = _lcp_color(lcp_ms)
    lcp_lbl     = _lcp_label(lcp_ms)

    # Angle narrative selon tag
    if tag == "perf":
        hero_subtitle = "Chaque seconde de délai coûte des conversions à vos campagnes Google Ads."
        section_title = "Impact sur vos campagnes publicitaires"
        impact_text   = (
            f"Un score mobile de {score_mobile}/100 place votre site dans le bas du classement "
            f"Google PageSpeed. Les visiteurs venus de vos annonces arrivent sur une page lente — "
            f"le taux de rebond augmente, votre ROAS baisse mécaniquement."
        )
    elif tag == "securite":
        hero_subtitle = "Votre infrastructure expose votre activité à des risques évitables."
        section_title = "Risques infrastructure identifiés"
        impact_text   = (
            f"Votre site tourne sur {cms} sans protection réseau détectée (CDN/WAF). "
            f"Cette configuration est vulnérable aux attaques DDoS et aux injections, "
            f"et peut entraîner une mise hors ligne de votre boutique sans préavis."
        )
    else:
        hero_subtitle = "Deux freins critiques détectés — performance mobile et infrastructure."
        section_title = "Double impact sur vos résultats"
        impact_text   = (
            f"Score mobile {score_mobile}/100 + infrastructure sans protection réseau : "
            f"vos campagnes Ads paient pour amener du trafic sur un site lent et vulnérable. "
            f"Les deux points se corrigent indépendamment, par ordre de priorité."
        )

    lcp_display = f"{lcp_ms/1000:.1f}s" if lcp_ms >= 1000 else f"{int(lcp_ms)}ms"
    fcp_display = f"{fcp_ms/1000:.1f}s" if fcp_ms >= 1000 else f"{int(fcp_ms)}ms" if fcp_ms else "—"

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Audit technique — {nom_entreprise}</title>
<meta name="robots" content="noindex,nofollow">
<style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;background:#f8f9fb;color:#1a1a1a;line-height:1.6}}
  a{{color:inherit;text-decoration:none}}

  .header{{background:#0d1117;padding:18px 32px;display:flex;justify-content:space-between;align-items:center}}
  .brand{{font-size:1.1rem;font-weight:800;color:#fff}}.brand span{{color:#10b981}}
  .header-meta{{font-size:12px;color:rgba(255,255,255,.45)}}

  .hero{{background:#0d1117;padding:52px 32px 60px;text-align:center;color:#fff}}
  .hero-tag{{display:inline-block;background:rgba(239,68,68,.12);border:1px solid rgba(239,68,68,.3);color:#ef4444;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.12em;padding:4px 14px;border-radius:20px;margin-bottom:20px}}
  .hero h1{{font-size:2rem;font-weight:800;margin-bottom:12px;line-height:1.25}}
  .hero p{{font-size:1rem;color:rgba(255,255,255,.6);max-width:560px;margin:0 auto}}

  .container{{max-width:820px;margin:0 auto;padding:0 24px}}

  .score-row{{display:flex;gap:16px;margin:-36px auto 0;padding:0 24px;max-width:820px;flex-wrap:wrap}}
  .score-card{{flex:1;min-width:180px;background:#fff;border-radius:14px;padding:24px 20px;text-align:center;box-shadow:0 4px 20px rgba(0,0,0,.07);border:1px solid #e5e7eb}}
  .score-big{{font-size:2.8rem;font-weight:800;line-height:1}}
  .score-label{{font-size:12px;color:#6b7280;margin-top:6px;font-weight:600;text-transform:uppercase;letter-spacing:.05em}}
  .score-sub{{font-size:11px;margin-top:4px;font-weight:700}}

  .section{{background:#fff;border-radius:14px;padding:28px 28px;margin:20px auto;max-width:820px;border:1px solid #e5e7eb;box-shadow:0 2px 12px rgba(0,0,0,.04)}}
  .section h2{{font-size:1rem;font-weight:700;margin-bottom:18px;padding-bottom:12px;border-bottom:1px solid #f1f5f9}}

  .metric-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px}}
  .metric{{background:#f8f9fb;border-radius:10px;padding:14px 16px;border:1px solid #e5e7eb}}
  .metric-val{{font-size:1.3rem;font-weight:800}}
  .metric-name{{font-size:11px;color:#6b7280;margin-top:3px;font-weight:600}}

  .infra-row{{display:flex;align-items:center;justify-content:space-between;padding:10px 0;border-bottom:1px solid #f1f5f9}}
  .infra-row:last-child{{border-bottom:none}}
  .infra-label{{font-size:14px;color:#374151;font-weight:500}}

  .impact-box{{background:#fef2f2;border:1px solid #fecaca;border-radius:10px;padding:18px 20px;margin-top:4px}}
  .impact-box.amber{{background:#fffbeb;border-color:#fde68a}}
  .impact-box.blue{{background:#eff6ff;border-color:#bfdbfe}}
  .impact-text{{font-size:14px;color:#374151;line-height:1.7}}

  .cta-section{{background:#0d1117;border-radius:14px;padding:36px 28px;text-align:center;margin:20px auto;max-width:820px}}
  .cta-section h2{{font-size:1.3rem;font-weight:800;color:#fff;margin-bottom:10px}}
  .cta-section p{{font-size:14px;color:rgba(255,255,255,.55);margin-bottom:24px}}
  .btn-cta{{display:inline-block;background:#10b981;color:#fff;padding:13px 32px;border-radius:8px;font-size:15px;font-weight:700;transition:background .2s}}
  .btn-cta:hover{{background:#059669}}

  .footer{{text-align:center;padding:28px;font-size:12px;color:#9ca3af}}
  .footer a{{color:#6b7280;font-weight:600}}

  @media(max-width:600px){{
    .hero h1{{font-size:1.5rem}}
    .score-row{{flex-direction:column}}
    .section{{padding:20px 16px}}
  }}
</style>
</head>
<body>

<header class="header">
  <div class="brand">Incidenx<span>.</span></div>
  <div class="header-meta">Rapport confidentiel · {date_audit}</div>
</header>

<div class="hero">
  <div class="hero-tag">Audit technique personnalisé</div>
  <h1>{nom_entreprise}</h1>
  <p>{hero_subtitle}</p>
</div>

<!-- Score cards -->
<div class="score-row">
  <div class="score-card">
    <div class="score-big" style="color:{score_color}">{score_mobile}<span style="font-size:1.2rem">/100</span></div>
    <div class="score-label">Score mobile</div>
    <div class="score-sub" style="color:{score_color}">{score_lbl}</div>
  </div>
  <div class="score-card">
    <div class="score-big" style="color:{lcp_color}">{lcp_display}</div>
    <div class="score-label">LCP (chargement principal)</div>
    <div class="score-sub" style="color:{lcp_color}">{lcp_lbl}</div>
  </div>
  <div class="score-card">
    <div class="score-big" style="color:#6b7280">{cms}</div>
    <div class="score-label">CMS détecté</div>
    <div class="score-sub" style="color:#9ca3af">{server}</div>
  </div>
</div>

<!-- Métriques détaillées -->
<div class="section" style="margin-top:32px">
  <h2>Métriques PageSpeed (mobile)</h2>
  <div class="metric-grid">
    <div class="metric">
      <div class="metric-val" style="color:{score_color}">{score_mobile}/100</div>
      <div class="metric-name">Score performance</div>
    </div>
    <div class="metric">
      <div class="metric-val" style="color:{lcp_color}">{lcp_display}</div>
      <div class="metric-name">LCP</div>
    </div>
    {"" if not fcp_ms else f'<div class="metric"><div class="metric-val">{fcp_display}</div><div class="metric-name">FCP</div></div>'}
    {"" if not blocking else f'<div class="metric"><div class="metric-val" style="color:#ef4444">{blocking}</div><div class="metric-name">Scripts bloquants</div></div>'}
    {"" if not page_kb else f'<div class="metric"><div class="metric-val">{page_kb} Ko</div><div class="metric-name">Poids page</div></div>'}
  </div>
</div>

<!-- Infrastructure -->
<div class="section">
  <h2>Infrastructure</h2>
  <div class="infra-row">
    <span class="infra-label">CMS</span>
    <span style="font-weight:600;font-size:14px">{cms}</span>
  </div>
  <div class="infra-row">
    <span class="infra-label">Serveur</span>
    <span style="font-weight:600;font-size:14px">{server}</span>
  </div>
  <div class="infra-row">
    <span class="infra-label">HTTPS</span>
    {_bool_badge(has_https, "Activé", "Absent")}
  </div>
  <div class="infra-row">
    <span class="infra-label">CDN (réseau de distribution)</span>
    {_bool_badge(has_cdn, "Présent", "Absent")}
  </div>
  <div class="infra-row">
    <span class="infra-label">WAF (pare-feu applicatif)</span>
    {_bool_badge(has_waf, "Présent", "Non détecté")}
  </div>
</div>

<!-- Impact -->
<div class="section">
  <h2>{section_title}</h2>
  <div class="impact-box{"" if tag == "perf" else " amber" if tag == "securite" else " blue"}">
    <p class="impact-text">{impact_text}</p>
  </div>
  {f'<p style="font-size:13px;color:#6b7280;margin-top:14px;font-style:italic">{reason}</p>' if reason else ""}
</div>

<!-- CTA -->
<div class="cta-section">
  <h2>20 minutes pour clarifier les priorités</h2>
  <p>Un appel sans engagement pour parcourir ce rapport ensemble<br>et identifier ce qui a le plus d'impact sur votre activité.</p>
  <a href="{calendly}" class="btn-cta">Réserver un créneau</a>
</div>

<footer class="footer">
  <p>Rapport préparé par <a href="https://incidenx.com">Jean-Marc DANSI — incidenx.com</a></p>
  <p style="margin-top:6px">contact@incidenx.com · Ce rapport est confidentiel et préparé uniquement pour {nom_entreprise}</p>
</footer>

</body>
</html>"""


# ─── Publication ──────────────────────────────────────────────────────────────

def _make_slug(site_web: str) -> str:
    """Génère un slug URL-safe depuis l'URL du site."""
    slug = re.sub(r"^https?://", "", site_web).rstrip("/")
    slug = re.sub(r"[^a-zA-Z0-9\-]", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug[:60].lower()


def generate_and_publish(lead_id: int) -> Optional[str]:
    """
    Génère le rapport HTML et le publie sur audit.incidenx.com/{slug}/.

    Lit les données depuis leads_audites + leads_bruts.
    Met à jour lien_rapport en DB si l'URL change.

    Returns:
        URL publique ou None si échec
    """
    from database.connection import get_conn

    try:
        with get_conn() as conn:
            row = conn.execute("""
                SELECT la.id, lb.donnees_audit, la.lien_rapport,
                       la.ceo_prenom, la.ceo_nom,
                       lb.tag_urgence,
                       lb.nom, lb.site_web
                FROM leads_audites la
                JOIN leads_bruts lb ON lb.id = la.lead_id
                WHERE lb.id = ?
            """, (lead_id,)).fetchone()

        if not row:
            logger.error(f"rapport_generator: lead {lead_id} introuvable")
            return None

        lead = dict(row)
        donnees = json.loads(lead.get("donnees_audit") or "{}")

        # Enrichir lead avec tag_urgence
        lead["tag_urgence"] = lead.get("tag_urgence") or lead.get("lb_tag") or "perf"

        # Slug basé sur le domaine
        slug = _make_slug(lead.get("site_web") or str(lead_id))

        # Générer le HTML
        html = generate_sniper_rapport_html(lead, donnees)

        # Publier via l'infra existante (batch GitHub → Vercel)
        from synthetiseur.github_publisher import push_audit_to_github
        result_url, _ = push_audit_to_github(slug, html)

        # Mettre à jour lien_rapport en DB si différent
        if result_url and result_url != lead.get("lien_rapport"):
            with get_conn() as conn:
                conn.execute(
                    "UPDATE leads_audites SET lien_rapport=? WHERE id=?",
                    (result_url, lead["id"])
                )
                conn.commit()

        logger.info(f"rapport_generator: publié → {result_url}")
        return result_url

    except Exception as e:
        logger.error(f"rapport_generator: erreur lead {lead_id} — {e}")
        return None
