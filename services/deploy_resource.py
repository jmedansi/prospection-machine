# -*- coding: utf-8 -*-
"""
deploy_resource.py — Interface pour déployer des ressources CTA sur GitHub Pages.

Utilisation :
    from deploy_resource import deploy_resource
    
    result = deploy_resource(
        slug="guide-facebook-monetisation-2025",
        title="Guide complet : Monétiser Facebook en 47 jours",
        content="# Introduction\n\nLe contenu complet ici...",
        theme="default"
    )
    # Returns: {"success": True, "url": "https://audit.incidenx.com/guide-facebook-monetisation-2025/", "slug": "..."}
    # ou: {"success": False, "error": "message"}

URL du endpoint HTTP (si actif) : POST /api/deploy-resource
"""
import os
import re
import logging
import requests

logger = logging.getLogger(__name__)

GITHUB_REPO = "jmedansi/incidenx-audit"
AUDIT_DOMAIN = os.getenv("AUDIT_DOMAIN", "audit.incidenx.com")


def _clean_slug(slug: str) -> str:
    """Nettoie le slug pour être URL-safe."""
    slug = re.sub(r'[^a-zA-Z0-9\s-]', '', slug.lower())
    slug = re.sub(r'\s+', '-', slug)
    return slug.strip('-')[:50]


def _generate_html(title: str, content: str, theme: str = "default") -> str:
    """Génère une page HTML CTA professionnelle."""
    theme_colors = {
        "default": {"primary": "#10b981", "bg": "#0d1117"},
        "blue": {"primary": "#3b82f6", "bg": "#1e3a5f"},
        "red": {"primary": "#ef4444", "bg": "#3b1e1e"},
        "purple": {"primary": "#8b5cf6", "bg": "#2e1a3b"},
    }
    colors = theme_colors.get(theme, theme_colors["default"])
    
    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="robots" content="index,follow">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;background:{colors['bg']};color:#fff;line-height:1.6}}
.header{{padding:1.5rem 2rem;display:flex;justify-content:space-between;align-items:center}}
.header-brand{{font-size:1.2rem;font-weight:700;color:#fff;text-decoration:none}}
.header-brand span{{color:{colors['primary']}}}
.hero{{padding:4rem 2rem;text-align:center}}
.hero-title{{font-size:2.5rem;font-weight:800;margin-bottom:1rem;line-height:1.2}}
.hero-content{{font-size:1.1rem;color:rgba(255,255,255,.8);max-width:700px;margin:0 auto;text-align:left}}
.hero-content h1{{font-size:1.8rem;margin:1.5rem 0 1rem}}
.hero-content h2{{font-size:1.4rem;margin:1.5rem 0 .75rem;color:{colors['primary']}}}
.hero-content p{{margin:.75rem 0}}
.hero-content ul,.hero-content ol{{margin:1rem 0;padding-left:1.5rem}}
.hero-content li{{margin:.5rem 0}}
.hero-content strong{{color:{colors['primary']}}}
.hero-content a{{color:{colors['primary']};text-decoration:underline}}
.cta{{text-align:center;padding:3rem 2rem;background:rgba(255,255,255,.05)}}
.cta-button{{display:inline-block;background:{colors['primary']};color:#fff;padding:1rem 2.5rem;border-radius:8px;font-size:1.1rem;font-weight:700;text-decoration:none;transition:transform .2s}}
.cta-button:hover{{transform:translateY(-2px)}}
.footer{{text-align:center;padding:2rem;color:rgba(255,255,255,.5);font-size:.9rem}}
.footer a{{color:{colors['primary']};text-decoration:none}}
@media (max-width:640px){{.hero-title{{font-size:1.8rem}}}}
</style>
</head>
<body>
<header class="header">
<a href="https://incidenx.com" class="header-brand">Incidenx<span>.</span></a>
</header>
<section class="hero">
<h1 class="hero-title">{title}</h1>
<div class="hero-content">{content}</div>
</section>
<section class="cta">
<a href="https://calendly.com/incidenx" class="cta-button">Réserver un appel gratuit</a>
</section>
<footer class="footer">
<a href="https://incidenx.com">Incidenx</a> · Ressources gratuites pour entrepreneurs
</footer>
</body>
</html>"""
    return html


def _get_gh_headers():
    token = os.getenv("GITHUB_TOKEN", os.getenv("GITHUB_ACCESS_TOKEN", ""))
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json"
    }


def _get_file_sha(path: str) -> str:
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    try:
        resp = requests.get(url, headers=_get_gh_headers(), timeout=10)
        if resp.status_code == 200:
            return resp.json().get("sha")
    except Exception as e:
        logger.warning(f"Error checking SHA for {path}: {e}")
    return None


def _commit_file(path: str, content: str, message: str) -> bool:
    import base64
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    content_b64 = base64.b64encode(content.encode('utf-8')).decode('utf-8')
    
    payload = {"message": message, "content": content_b64, "branch": "main"}
    sha = _get_file_sha(path)
    if sha:
        payload["sha"] = sha
    
    try:
        resp = requests.put(url, headers=_get_gh_headers(), json=payload, timeout=30)
        return resp.status_code in [200, 201]
    except Exception as e:
        logger.error(f"Error committing {path}: {e}")
        return False


def deploy_resource(slug: str, title: str, content: str, theme: str = "default") -> dict:
    """
    Déploie une ressource CTA sur GitHub Pages.
    
    Args:
        slug: Identifiant unique (ex: "guide-facebook-monetisation-2025")
        title: Titre de la ressource
        content: Contenu Markdown/HTML
        theme: Thème_OPTIONNEL ("default", "blue", "red", "purple")
    
    Returns:
        dict: {"success": True, "url": "...", "slug": "..."}
              ou {"success": False, "error": "..."}
    """
    if not slug or not title or not content:
        return {"success": False, "error": "Missing required fields: slug, title, content"}
    
    slug = _clean_slug(slug)
    
    try:
        html = _generate_html(title, content, theme)
        
        if _commit_file(f"{slug}/index.html", html, f"Deploy: {slug}"):
            public_url = f"https://{AUDIT_DOMAIN}/{slug}/"
            logger.info(f"✅ Resource deployed: {public_url}")
            return {"success": True, "url": public_url, "slug": slug}
        else:
            return {"success": False, "error": "Failed to commit to GitHub"}
    except Exception as e:
        logger.error(f"Deploy error: {e}")
        return {"success": False, "error": str(e)}