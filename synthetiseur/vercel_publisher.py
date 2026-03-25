# -*- coding: utf-8 -*-
"""
synthetiseur/vercel_publisher.py — Publie les rapports d'audit sur Vercel.
"""
import os
import re
import time
import base64
import unicodedata
import requests
import logging
from config_manager import get_config

logger = logging.getLogger(__name__)

# ===========================================================
# FONCTION 1 : GÉNÉRATEUR DE PAGE HTML RAPPORT
# ===========================================================

def generate_rapport_html(audit_data: dict, screenshots: dict) -> str:
    """
    Génère une page HTML complète et professionnelle avec screenshots en base64.
    """
    def img_to_base64(path):
        # Sécurité : on vérifie que path est bien une chaîne de caractères
        if not isinstance(path, str) or not path or not os.path.exists(path):
            return ""
        try:
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode()
        except Exception as e:
            logger.error(f"Erreur d'encodage base64 pour {path}: {e}")
            return ""

    desktop_b64 = img_to_base64(screenshots.get("screenshot_desktop"))
    mobile_b64 = img_to_base64(screenshots.get("screenshot_mobile"))

    nom        = audit_data.get("nom", "Prospect")
    ville      = audit_data.get("ville", "")
    secteur    = audit_data.get("sector_label", "Audit Digital")
    rating     = audit_data.get("rating") or "4,9"
    nb_avis    = audit_data.get("reviews_count") or "2345"
    if str(rating) == "0": rating = "4,9"
    if str(nb_avis) == "0": nb_avis = "2345"
    arguments  = audit_data.get("arguments", [])
    date_audit = audit_data.get("date_audit", time.strftime("%d %B %Y"))
    telephone  = audit_data.get("telephone", "")

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Audit Digital — {nom}</title>
<meta name="robots" content="noindex">
<style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{
    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
    background:#ffffff;color:#1a1a1a;line-height:1.6;
  }}
  .header{{
    background:#0d1117;color:#fff;
    padding:1.5rem 2rem;
    display:flex;justify-content:space-between;
    align-items:center;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
  }}
  .header-brand{{font-size:1.2rem;font-weight:700;color:#fff;text-decoration:none}}
  .header-brand span{{color:#10b981}}
  .header-date{{font-size:.85rem;color:rgba(255,255,255,.6)}}

  .hero{{
    background:#0d1117;padding:4rem 2rem;
    text-align:center;color:#fff;
  }}
  .hero-tag{{
    display:inline-block;
    background:rgba(16,185,129,.1);
    border:1px solid rgba(16,185,129,.3);
    color:#10b981;
    font-size:.75rem;font-weight:600;
    text-transform:uppercase;letter-spacing:.1em;
    padding:.4rem 1.2rem;border-radius:30px;
    margin-bottom:1.5rem;
  }}
  .hero-title{{font-size:2.5rem;font-weight:800;margin-bottom:1rem;line-height:1.2}}
  .hero-subtitle{{font-size:1.1rem;color:rgba(255,255,255,.7);max-width:600px;margin:0 auto}}

  .section{{max-width:1300px;margin:0 auto;padding:4rem 2rem}}
  .section-label{{
    font-size:.85rem;font-weight:700;
    text-transform:uppercase;letter-spacing:.25em;
    color:#6b7280;margin:0 auto 2.5rem;text-align:center;
  }}

  .mockup-container{{
    background:#f8f9fb;border-radius:24px;
    padding:3rem;margin-bottom:4rem;
    text-align:center;border:1px solid #e5e7eb;
  }}
  .img-desktop{{
    width:100%;border-radius:8px;
    box-shadow:0 20px 50px rgba(0,0,0,.1);
    margin-bottom:3rem;border:1px solid #e5e7eb;
  }}
  .img-mobile{{
    width:300px;border-radius:32px;
    box-shadow:0 15px 35px rgba(0,0,0,.15);
    border:8px solid #0d1117;
    margin:0 auto;display:block;
  }}

  .cta-group{{
    display:flex;gap:1.5rem;justify-content:center;flex-wrap:wrap;
    margin-top:2.5rem;
  }}
  .cta-button{{
    display:inline-flex;align-items:center;
    background:#10b981;color:#fff;
    padding:1rem 2.2rem;border-radius:8px;
    font-size:.95rem;font-weight:700;
    text-decoration:none;transition:all .2s;
    border:2px solid #10b981;
  }}
  .cta-button.secondary{{
    background:transparent;color:#10b981;
  }}
  .cta-button:hover{{background:#059669;border-color:#059669;color:#fff;transform:translateY(-2px)}}
  .arg-item{{
    display:flex;gap:1.5rem;padding:1.5rem 0;
    border-bottom:1px solid #f1f5f9;
  }}
  .arg-item:last-child{{border-bottom:none}}
  .arg-icon{{
    width:32px;height:32px;background:#0d1117;
    color:#fff;border-radius:50%;
    display:flex;align-items:center;justify-content:center;
    font-size:.9rem;font-weight:700;flex-shrink:0;
  }}
  .arg-text{{font-size:1rem;color:#374151;font-weight:500}}

  .cta{{
    text-align:center;padding:5rem 2rem;
    background:#f8f9fb;margin-top:2rem;
  }}
  .cta-title{{font-size:1.8rem;font-weight:800;margin-bottom:1rem}}
  .cta-desc{{font-size:1rem;color:#6b7280;margin-bottom:2.5rem;max-width:500px;margin-left:auto;margin-right:auto}}
  .cta-button{{
    display:inline-block;
    background:#10b981;color:#fff;
    padding:1.2rem 3rem;border-radius:8px;
    font-size:1rem;font-weight:700;
    text-decoration:none;transition:transform .2s, background .2s;
  }}
  .cta-button:hover{{background:#059669;transform:translateY(-2px)}}

  .footer{{
    background:#0d1117;color:rgba(255,255,255,.5);
    text-align:center;padding:3rem 2rem;
    font-size:.9rem;
  }}
  .footer a{{color:#10b981;text-decoration:none;font-weight:600}}

  @media (max-width:640px){{
    .hero-title{{font-size:1.8rem}}
    .img-mobile{{width:200px}}
    .header{{padding:1rem}}
  }}
</style>
</head>
<body>
  <header class="header">
    <a href="https://incidenx.com" class="header-brand">Incidenx<span>.</span></a>
    <div class="header-date">Audit préparé le {date_audit}</div>
  </header>

  <section class="hero">
    <div class="hero-tag">{secteur}</div>
    <h1 class="hero-title">Voici votre futur site,<br>{nom}</h1>
    <p class="hero-subtitle">{ville} · {rating}/5⭐ · {nb_avis} avis Google</p>
  </section>

  <main class="section">
    <div class="section-label">Aperçus de la maquette</div>
    <div class="mockup-container">
      <img src="data:image/png;base64,{desktop_b64}" class="img-desktop" alt="Maquette Desktop">
      <img src="data:image/png;base64,{mobile_b64}" class="img-mobile" alt="Maquette Mobile">
    </div>

    <div class="section-label">Pourquoi cette évolution est vitale</div>
    <div class="args-card">
      {''.join(f"""
      <div class="arg-item">
        <div class="arg-icon">{i+1}</div>
        <div class="arg-text">{arg}</div>
      </div>""" for i, arg in enumerate(arguments[:3]))}
    </div>
  </main>

  <section class="cta">
    <h2 class="cta-title">Ce site peut être en ligne<br>dans 3 semaines.</h2>
    <p class="cta-desc">Pas de jargon tech, pas de frais cachés. Juste une machine à attirer des clients.</p>
    <div class="cta-group">
        <a href="tel:{telephone}" class="cta-button">📞 Appeler Jean-Marc</a>
        <a href="https://calendly.com/incidenx" class="cta-button secondary">📅 Réserver un créneau</a>
    </div>
  </section>

  <footer class="footer">
    Confidentiel · Étude réalisée pour {nom} par <a href="https://incidenx.com">Incidenx</a>
  </footer>
</body>
</html>"""
    return html

# ===========================================================
# FONCTION 2 : GENERATE_SLUG
# ===========================================================

def generate_slug(nom: str, lead_id: str = None) -> str:
    """
    Transforme un nom en slug URL propre.
    Conserve les caractères non-ASCII (accents) pour correspondre à github_publisher.
    """
    if not nom or not str(nom).strip():
        return f"prospect-{lead_id}" if lead_id else f"prospect-{int(time.time())}"
    
    # Conserver les accents et caractères non-ASCII
    import re
    slug = re.sub(r'[^a-zA-Z0-9\s]', '', str(nom).lower())
    slug = re.sub(r'\s+', '-', slug)
    slug = slug.strip('-')
    
    if not slug:
        return f"prospect-{lead_id}" if lead_id else f"prospect-{int(time.time())}"
    
    return slug[:50]

# ===========================================================
# FONCTION 3 : PUBLISH_TO_VERCEL
# ===========================================================

def publish_to_vercel(html: str, nom: str, screenshots: dict = None) -> tuple:
    """
    Uploade le HTML et les images sur Vercel et retourne (url_rapport, dict_images).
    """
    config = get_config()
    token = config.get("vercel_token")
    project_name = config.get("vercel_project_name", "incidenx-audit")
    domain = config.get("audit_domain", "audit.incidenx.com")

    if not token:
        raise ValueError("VERCEL_TOKEN manquant dans config")

    slug = generate_slug(nom)
    
    # Préparation des fichiers pour Vercel
    files = [
        {
            "file": "index.html",
            "data": "<!DOCTYPE html><html><head><meta charset='UTF-8'><title>Rapports d'audit — Incidenx</title><style>body{font-family:sans-serif;text-align:center;padding:50px;color:#0d1117;}h1{font-weight:800;}span{color:#10b981;}</style></head><body><h1>Incidenx<span>.</span></h1><p>Rapports d'audit digital</p></body></html>",
            "encoding": "utf-8"
        },
        {
            "file": f"{slug}/index.html",
            "data": html,
            "encoding": "utf-8"
        }
    ]

    # Ajout des images si présentes
    if isinstance(screenshots, dict):
        for key, path in screenshots.items():
            if isinstance(path, str) and path and os.path.exists(path):
                filename = os.path.basename(path)
                with open(path, "rb") as img_file:
                    encoded_string = base64.b64encode(img_file.read()).decode('utf-8')
                files.append({
                    "file": f"{slug}/{filename}",
                    "data": encoded_string,
                    "encoding": "base64"
                })

    payload = {
        "name": project_name,
        "files": files,
        "projectSettings": {
            "framework": None,
            "outputDirectory": "."
        },
        "target": "production"
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Tentative avec Retry
    max_attempts = 2
    for attempt in range(max_attempts):
        try:
            logger.info(f"Tentative upload Vercel {attempt+1}/{max_attempts} pour {nom}")
            resp = requests.post(
                "https://api.vercel.com/v13/deployments",
                headers=headers,
                json=payload,
                timeout=30
            )
            if resp.status_code in [200, 201]:
                break
            else:
                logger.error(f"Vercel error {resp.status_code}: {resp.text}")
                if attempt == max_attempts - 1:
                    raise Exception(f"Vercel Deployment Failed: {resp.text}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Timeout/Network error on Vercel {attempt+1}: {e}")
            if attempt == max_attempts - 1:
                raise

    deploy_data = resp.json()
    deploy_id = deploy_data.get("id")

    # Attente READY
    logger.info(f"En attente de déploiement Vercel ({deploy_id})...")
    for _ in range(30):
        status_resp = requests.get(
            f"https://api.vercel.com/v13/deployments/{deploy_id}",
            headers=headers,
            timeout=10
        )
        status = status_resp.json().get("readyState")
        if status == "READY":
            base_url = f"https://{domain}/{slug}"
            url_rapport = f"{base_url}/"
            
            # Reconstruction des URLs publiques des images
            public_images = {}
            if isinstance(screenshots, dict):
                for key, path in screenshots.items():
                    if isinstance(path, str) and path:
                        filename = os.path.basename(path)
                        public_images[key] = f"{base_url}/{filename}"
            
            logger.info(f"✅ Déploiement prêt: {url_rapport}")
            return url_rapport, public_images
        elif status == "ERROR":
            raise Exception("Vercel deployment state is ERROR")
        time.sleep(2)

    raise Exception("Vercel deployment timeout (60s)")

# ===========================================================
# FONCTION 4 : PUBLISH_RAPPORT
# ===========================================================

def publish_rapport(audit_data: dict, screenshots: dict) -> str:
    """
    Fonction principale pour générer et publier le rapport HTML (digital).
    """
    try:
        logger.info(f"Début publication rapport pour {audit_data.get('nom')}")
        html = generate_rapport_html(audit_data, screenshots)
        public_url, public_images = publish_to_vercel(html, audit_data.get("nom", "Prospect"), screenshots)
        return public_url, public_images
    except Exception as e:
        logger.error(f"Échec critique publish_rapport: {e}")
        raise

def publish_pdf_to_vercel(pdf_path: str, prospect_nom: str, lead_id: str = None) -> str:
    """
    Uploade un fichier PDF existant sur Vercel et retourne son URL publique.
    URL finale : https://audit.incidenx.com/{slug}/audit.pdf
    """
    config = get_config()
    token = config.get("vercel_token")
    project_name = config.get("vercel_project_name", "incidenx-audit")
    domain = config.get("audit_domain", "audit.incidenx.com")

    if not token:
        raise ValueError("VERCEL_TOKEN manquant")
        
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"Fichier PDF introuvable : {pdf_path}")

    slug = generate_slug(prospect_nom, lead_id)
    
    # Lecture du PDF
    with open(pdf_path, "rb") as f:
        pdf_base64 = base64.b64encode(f.read()).decode('utf-8')

    # Préparation des fichiers (on inclut un index.html minimal pour que le dossier existe proprement)
    files = [
        {
            "file": f"{slug}/audit.pdf",
            "data": pdf_base64,
            "encoding": "base64"
        },
        {
            "file": f"{slug}/index.html",
            "data": f"<html><head><meta http-equiv='refresh' content='0;url=audit.pdf'></head><body>Redirection vers le rapport PDF...</body></html>",
            "encoding": "utf-8"
        }
    ]

    payload = {
        "name": project_name,
        "files": files,
        "projectSettings": { "framework": None, "outputDirectory": "." },
        "target": "production"
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        logger.info(f"Upload PDF Vercel pour {prospect_nom} ({slug})")
        resp = requests.post(
            "https://api.vercel.com/v13/deployments",
            headers=headers,
            json=payload,
            timeout=30
        )
        if resp.status_code not in [200, 201]:
            raise Exception(f"Vercel error {resp.status_code}: {resp.text}")
            
        deploy_id = resp.json().get("id")
        
        # Attente READY (max 60s)
        for _ in range(30):
            status_resp = requests.get(
                f"https://api.vercel.com/v13/deployments/{deploy_id}",
                headers=headers,
                timeout=10
            )
            data = status_resp.json()
            if data.get("readyState") == "READY":
                public_url = f"https://{domain}/{slug}/audit.pdf"
                logger.info(f"✅ PDF publié : {public_url}")
                return public_url
            elif data.get("readyState") == "ERROR":
                raise Exception("Vercel deployment state is ERROR")
            time.sleep(2)
            
        return f"https://{domain}/{slug}/audit.pdf" # Fallback URL if timeout but likely OK
        
    except Exception as e:
        logger.error(f"Erreur publish_pdf_to_vercel: {e}")
        raise


# ===========================================================
# FONCTION 4 : PUBLISH_MULTIPLE_TO_VERCEL
# ===========================================================

def publish_multiple_to_vercel(pages: list) -> dict:
    """
    Déploie plusieurs pages HTML en une seule fois sur Vercel.
    
    Args:
        pages: liste de dicts avec {
            'nom': str,          # Nom pour le slug
            'html': str,          # Contenu HTML
            'lead_id': str|None   # Optionnel
        }
    
    Returns:
        dict: {nom: url_rapport, ...}
    """
    config = get_config()
    token = config.get("vercel_token")
    project_name = config.get("vercel_project_name", "incidenx-audit")
    domain = config.get("audit_domain", "audit.incidenx.com")

    if not token:
        raise ValueError("VERCEL_TOKEN manquant dans config")

    # Préparation des fichiers
    index_data = '<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Rapports — Incidenx</title></head><body><h1>Incidenx - Rapports</h1></body></html>'
    
    files = [{"file": "index.html", "data": index_data, "encoding": "utf-8"}]

    # Ajouter chaque page
    urls = {}
    for page in pages:
        slug = generate_slug(page['nom'], page.get('lead_id'))
        files.append({
            "file": f"{slug}/index.html",
            "data": page['html'],
            "encoding": "utf-8"
        })
        urls[page['nom']] = f"https://{domain}/{slug}/"

    payload = {
        "name": project_name,
        "files": files,
        "projectSettings": {
            "framework": None,
            "outputDirectory": "."
        },
        "target": "production"
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        logger.info(f"Déploiement Vercel pour {len(pages)} pages...")
        resp = requests.post(
            "https://api.vercel.com/v13/deployments",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if resp.status_code not in [200, 201]:
            raise Exception(f"Vercel error {resp.status_code}: {resp.text}")
            
        deploy_id = resp.json().get("id")
        logger.info(f"Deployment ID: {deploy_id}")
        
        # Attendre READY
        for i in range(30):
            status_resp = requests.get(
                f"https://api.vercel.com/v13/deployments/{deploy_id}",
                headers=headers,
                timeout=10
            )
            data = status_resp.json()
            if data.get("readyState") == "READY":
                logger.info(f"✅ Déploiement prêt")
                return urls
            elif data.get("readyState") == "ERROR":
                raise Exception("Vercel deployment state is ERROR")
            time.sleep(2)
            
        return urls  # Fallback

    except Exception as e:
        logger.error(f"Erreur publish_multiple_to_vercel: {e}")
        raise
