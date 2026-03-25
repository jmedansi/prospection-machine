# -*- coding: utf-8 -*-
"""
Module synthetiseur/image_storage.py
Gestion du stockage des images via GitHub Releases (plus approprié pour les binaires)
"""
import os
import base64
import requests
import logging
from typing import Dict, Optional, Tuple
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", os.getenv("GITHUB_ACCESS_TOKEN", ""))
GITHUB_REPO = "jmedansi/incidenx-audit"

def _get_gh_headers():
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }

def get_or_create_release(tag_name: str = "screenshots") -> dict:
    """Obtient ou crée une release dédiée au stockage des screenshots"""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/tags/{tag_name}"
    
    try:
        resp = requests.get(url, headers=_get_gh_headers(), timeout=10)
        if resp.status_code == 200:
            logger.info(f"Release '{tag_name}' trouvée")
            return resp.json()
    except Exception as e:
        logger.warning(f"Erreur lors de la vérification de la release {tag_name}: {e}")
    
    # Créer la release si elle n'existe pas
    logger.info(f"Création de la release '{tag_name}'")
    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases"
    data = {
        "tag_name": tag_name,
        "name": f"Stockage des screenshots - {datetime.now().strftime('%Y-%m-%d')}",
        "body": "Release dédiée au stockage des screenshots des audits",
        "draft": False,
        "prerelease": False
    }
    
    try:
        resp = requests.post(url, headers=_get_gh_headers(), json=data, timeout=10)
        if resp.status_code == 201:
            logger.info(f"Release '{tag_name}' créée avec succès")
            return resp.json()
        else:
            logger.error(f"Échec de création de la release: {resp.status_code} - {resp.text}")
            raise Exception(f"Impossible de créer la release: {resp.status_code}")
    except Exception as e:
        logger.error(f"Exception lors de la création de la release: {e}")
        raise

def upload_image_to_release(image_path: str, release_id: int) -> Optional[str]:
    """Upload une image vers une release GitHub et retourne l'URL de téléchargement"""
    if not os.path.exists(image_path):
        logger.error(f"Fichier image introuvable: {image_path}")
        return None
        
    # Vérifier la taille (limite GitHub: 100MB, mais on reste raisonnable)
    file_size = os.path.getsize(image_path)
    if file_size > 5 * 1024 * 1024:  # 5MB max par image
        logger.warning(f"Image trop grande ({file_size} bytes): {image_path}")
        # On pourrait compresser ici si nécessaire
    
    # L'URL d'upload est différente de l'URL de l'API standard
    owner, repo = GITHUB_REPO.split('/')
    url = f"https://uploads.github.com/repos/{owner}/{repo}/releases/{release_id}/assets"
    
    # Obtenir le nom du fichier
    filename = os.path.basename(image_path)
    
    headers = _get_gh_headers()
    headers["Content-Type"] = "application/octet-stream"
    
    try:
        with open(image_path, "rb") as f:
            image_data = f.read()
        
        params = {"name": filename}
        resp = requests.post(url, headers=headers, params=params, data=image_data, timeout=30)
        
        if resp.status_code == 201:
            asset_data = resp.json()
            download_url = asset_data.get("browser_download_url")
            logger.info(f"Image uploaded successfully to GitHub Release: {filename} -> {download_url}")
            return download_url
        elif resp.status_code == 422:
            # L'asset existe déjà, on récupère l'URL existante
            logger.info(f"L'image {filename} existe déjà dans la release, récupération de l'URL...")
            release_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/{release_id}"
            release_resp = requests.get(release_url, headers=_get_gh_headers(), timeout=10)
            if release_resp.status_code == 200:
                assets = release_resp.json().get("assets", [])
                for asset in assets:
                    if asset["name"] == filename:
                        return asset["browser_download_url"]
            return None
        else:
            logger.error(f"Échec d'upload de l'image {filename} ({resp.status_code}): {resp.text}")
            return None
            
    except Exception as e:
        logger.error(f"Exception lors de l'upload de l'image {filename}: {e}")
        return None

def store_screenshots(slug: str, screenshots: Dict[str, str]) -> Dict[str, str]:
    """
    Stocke les screenshots dans une release GitHub dédiée
    Retourne un dictionnaire mapping les clés aux URLs publiques
    """
    if not screenshots:
        return {}
        
    try:
        # Obtenir ou créer la release de stockage
        release = get_or_create_release("audit-screenshots")
        release_id = release.get("id")
        
        if not release_id:
            logger.error("Impossible d'obtenir l'ID de la release")
            return {}
            
        # Upload chaque screenshot
        stored_urls = {}
        for key, local_path in screenshots.items():
            if local_path and os.path.exists(local_path):
                download_url = upload_image_to_release(local_path, release_id)
                if download_url:
                    stored_urls[key] = download_url
                else:
                    logger.warning(f"Échec de stockage du screenshot {key}: {local_path}")
            else:
                logger.warning(f"Screenshot introuvable ou chemin invalide: {local_path}")
                
        return stored_urls
        
    except Exception as e:
        logger.error(f"Erreur lors du stockage des screenshots pour {slug}: {e}")
        return {}

# Fonction de compatibilité avec l'interface existante
def push_audit_to_github_with_external_storage(slug: str, html_content: str, screenshots: dict = None) -> tuple:
    """
    Version modifiée de push_audit_to_github qui utilise un stockage externe pour les images
    Retourne (url_publique, images_dict) où images_dict contient les URLs réelles des images
    """
    if screenshots is None:
        screenshots = {}
    
    # Stocker les screenshots externement
    stored_screenshots = store_screenshots(slug, screenshots)
    
    # Pour l'URL publique, on utilise toujours le même schéma (le HTML sera dans le repo)
    public_url = f"https://{os.getenv('AUDIT_DOMAIN', 'audit.incidenx.com')}/{slug}/"
    
    # On retourne les URLs réelles des images stockées
    return public_url, stored_screenshots