# -*- coding: utf-8 -*-
"""
Module synthetiseur/github_publisher.py
Pousse les rapports HTML sur GitHub en mode batch.
"""
import os
import base64
import time
import json
import threading
import requests
import logging
from dotenv import load_dotenv
from typing import Optional, Dict, Tuple

# Import du module de stockage externe d'images
# TEMPORAIREMENT DÉSACTIVÉ (problème de URLs 404 sur les releases GitHub)
try:
    from .image_storage import store_screenshots, push_audit_to_github_with_external_storage
    EXTERNAL_STORAGE_AVAILABLE = False  # Désactivé temporairement
except ImportError:
    EXTERNAL_STORAGE_AVAILABLE = False
    logger.warning("Module image_storage non disponible, utilisation du stockage en Base64")

load_dotenv()
logger = logging.getLogger(__name__)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", os.getenv("GITHUB_ACCESS_TOKEN", ""))
GITHUB_REPO = "jmedansi/incidenx-audit"
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")

VERCEL_TOKEN = os.getenv("VERCEL_TOKEN")
VERCEL_PROJECT_NAME = os.getenv("VERCEL_PROJECT_NAME", "incidenx-audit")
AUDIT_DOMAIN = os.getenv("AUDIT_DOMAIN", "audit.incidenx.com")

BATCH_SIZE = int(os.getenv("GITHUB_BATCH_SIZE", "10"))
BATCH_INTERVAL = int(os.getenv("GITHUB_BATCH_INTERVAL", "300"))

_queue_lock = threading.Lock()
_pending_queue = []
_batch_thread = None
_last_flush = time.time()


def generate_slug(nom: str) -> str:
    """Génère un slug URL-safe depuis le nom."""
    import re
    slug = re.sub(r'[^a-zA-Z0-9\s]', '', nom.lower())
    slug = re.sub(r'\s+', '-', slug)
    slug = slug.strip('-')
    return slug[:50]


def _get_gh_headers():
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json"
    }


def _get_file_sha(path: str) -> Optional[str]:
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    try:
        resp = requests.get(url, headers=_get_gh_headers(), params={"ref": GITHUB_BRANCH}, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("sha")
    except Exception as e:
        logger.warning(f"Error checking SHA for {path}: {e}")
    return None


def _commit_files(files: list, message: str) -> bool:
    """
    Commit several files to GitHub.
    Expected format for each file in 'files':
    {
        "path": "slug/file.ext",
        "content": "string or bytes",
        "is_binary": True/False
    }
    """
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/"
    max_retries = 3
    retry_delay = 2  # seconds
    
    # Vérifier la taille totale des fichiers (éviter de dépasser les limites GitHub)
    total_size = 0
    for file_info in files:
        content = file_info["content"]
        if isinstance(content, str):
            # Estimer la taille en base64 (environ 33% d'overhead)
            total_size += len(content) * 3 // 4
        else:
            total_size += len(content)
    
    # GitHub a une limite de 100MB par fichier, mais on reste prudents avec 50MB par batch
    if total_size > 50 * 1024 * 1024:  # 50MB
        logger.warning(f"Batch size too large ({total_size} bytes), skipping commit")
        return False
    
    success_count = 0
    for file_info in files:
        path = file_info["path"]
        content = file_info["content"]
        
        if file_info.get("is_binary"):
            if isinstance(content, str):
                # Probablement déjà du base64
                content_base64 = content
            else:
                content_base64 = base64.b64encode(content).decode('utf-8')
        else:
            # Texte (HTML)
            content_base64 = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        
        payload = {
            "message": message,
            "content": content_base64,
            "branch": GITHUB_BRANCH
        }
        
        sha = _get_file_sha(path)
        if sha:
            payload["sha"] = sha
        
        file_url = f"{url}{path}"
        
        # Tentatives de commit avec reprise
        committed = False
        for attempt in range(max_retries):
            try:
                resp = requests.put(file_url, headers=_get_gh_headers(), json=payload, timeout=30)
                if resp.status_code in [200, 201]:
                    logger.info(f"Successfully committed {path} to GitHub")
                    success_count += 1
                    committed = True
                    break
                elif resp.status_code == 409:
                    # Conflit, on retry après avoir récupéré le SHA le plus récent
                    logger.warning(f"Conflict for {path}, attempt {attempt+1}/{max_retries}")
                    sha = _get_file_sha(path)
                    if sha:
                        payload["sha"] = sha
                    else:
                        logger.error(f"Could not get SHA for {path} after conflict")
                        break
                else:
                    logger.warning(f"Failed to commit {path}: {resp.status_code} - {resp.text[:200]}")
                    if attempt < max_retries - 1:
                        logger.info(f"Retrying in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                    else:
                        logger.error(f"Max retries exceeded for {path}")
            except Exception as e:
                logger.error(f"Error committing {path} (attempt {attempt+1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"Max retries exceeded for {path}")
        
        if not committed:
            logger.error(f"Failed to commit {path} after {max_retries} attempts")
    
    # Considérer le batch comme réussi si au moins la moitié des fichiers ont été commités
    return success_count >= len(files) // 2


def _flush_batch():
    global _pending_queue, _last_flush
    
    with _queue_lock:
        if not _pending_queue:
            return
        
        reports = _pending_queue.copy()
        _pending_queue = []
        _last_flush = time.time()
    
    # Transformer les rapports en une liste plate de fichiers
    files_to_commit = []
    slugs = []
    
    for report in reports:
        slug = report["slug"]
        slugs.append(slug)
        
        html_content = report["content"]
        screenshots = report.get("screenshots", {})
        
        # 1. Remplacer les URLs absolues par des chemins relatifs pour le repo GitHub
        # (Si on n'utilise pas le stockage externe)
        for key, local_path in screenshots.items():
            if not local_path:
                continue
            
            # S'assurer que le chemin est absolu pour le worker thread
            if not os.path.isabs(local_path):
                # On assume que c'est relatif au root du projet
                abs_path = os.path.abspath(local_path)
            else:
                abs_path = local_path
            
            if os.path.exists(abs_path):
                filename = os.path.basename(abs_path)
                # L'URL générée par reporter/main.py est de type https://audit.incidenx.com/slug/filename
                full_url = f"https://{AUDIT_DOMAIN}/{slug}/{filename}"
                
                # Dans l'index.html qui est dans le dossier /slug/, le chemin doit être juste 'filename'
                if full_url in html_content:
                    html_content = html_content.replace(full_url, filename)
                    logger.error(f"DEBUG: Successfully replaced {full_url} with {filename}")
                else:
                    logger.error(f"DEBUG: URL {full_url} NOT FOUND in HTML content (length {len(html_content)})")
                    # Log a small part of the HTML to see what's inside
                    if "src=" in html_content:
                        idx = html_content.find("src=")
                        logger.error(f"DEBUG: HTML excerpt near src: {html_content[idx:idx+100]}")
                
                # Backup: remplacer aussi le chemin local s'il est par erreur dans le HTML
                local_path_norm = abs_path.replace('\\', '/')
                if local_path_norm in html_content:
                    html_content = html_content.replace(local_path_norm, filename)
                elif abs_path in html_content:
                    html_content = html_content.replace(abs_path, filename)
            else:
                logger.error(f"DEBUG: Screenshot file NOT FOUND for {slug}: {abs_path}")
        
        # Le fichier HTML modifié
        files_to_commit.append({
            "path": report["path"],
            "content": html_content,
            "is_binary": False
        })
        
        # Les screenshots
        for key, local_path in screenshots.items():
            if not local_path:
                continue
            
            abs_path = os.path.abspath(local_path) if not os.path.isabs(local_path) else local_path
            
            if os.path.exists(abs_path):
                try:
                    with open(abs_path, "rb") as f:
                        img_data = f.read()
                    files_to_commit.append({
                        "path": f"{slug}/{os.path.basename(abs_path)}",
                        "content": img_data,
                        "is_binary": True
                    })
                    logger.debug(f"Queued screenshot for commit: {slug}/{os.path.basename(abs_path)}")
                except Exception as e:
                    logger.error(f"Error reading screenshot {abs_path}: {e}")
            else:
                # Déjà loggé au dessus
                pass
    
    count = len(reports)
    message = f"Batch: {count} audits - {', '.join(slugs[:3])}"
    if count > 3:
        message += f" (+{count - 3} others)"
    
    logger.info(f"Flushing batch of {count} reports ({len(files_to_commit)} files) to GitHub")
    
    if _commit_files(files_to_commit, message):
        logger.info(f"Batch committed successfully")
    else:
        logger.error(f"Batch commit failed")
        # Note: on ne re-queue pas ici pour éviter des boucles infinies sur erreurs 404/permissions


def _batch_worker():
    global _batch_thread, _last_flush
    
    while True:
        time.sleep(30)
        
        with _queue_lock:
            should_flush = (
                len(_pending_queue) >= BATCH_SIZE or
                (len(_pending_queue) > 0 and time.time() - _last_flush >= BATCH_INTERVAL)
            )
        
        if should_flush:
            _flush_batch()


def start_batch_worker():
    global _batch_thread
    if _batch_thread is None:
        _batch_thread = threading.Thread(target=_batch_worker, daemon=True)
        _batch_thread.start()
        logger.info("GitHub batch worker started")


def flush_pending_reports():
    _flush_batch()


def push_audit_to_github(slug: str, html_content: str, screenshots: "dict | None" = None) -> tuple:
    """
    Ajoute le rapport à la file d'attente pour commit batch.
    Utilise le stockage externe pour les images quand disponible.
    
    Returns:
        (url_publique, images_dict)
    """
    if screenshots is None:
        screenshots = {}
    
    # Utiliser le stockage externe si disponible
    if EXTERNAL_STORAGE_AVAILABLE and screenshots:
        try:
            stored_screenshots = store_screenshots(slug, screenshots)
            # Remplacer les URLs dans le HTML par les URLs de la Release
            for key, web_url in stored_screenshots.items():
                # On cherche l'URL par défaut générée par reporter/main.py
                filename = os.path.basename(screenshots.get(key, ""))
                old_url = f"https://{AUDIT_DOMAIN}/{slug}/{filename}"
                if old_url in html_content:
                    html_content = html_content.replace(old_url, web_url)
                    logger.info(f"Replaced {old_url} with external {web_url}")
            
            logger.info(f"Using external storage for {len(stored_screenshots)} screenshots")
            # Une fois les URLs remplacées, on CONTINUE pour publier le HTML modifié sur GitHub
        except Exception as e:
            logger.error(f"Error using external storage, falling back to repository storage: {e}")
    
    public_url = f"https://{AUDIT_DOMAIN}/{slug}/"
    
    with _queue_lock:
        _pending_queue.append({
            "slug": slug,
            "path": f"{slug}/index.html",
            "content": html_content,
            "screenshots": screenshots
        })
        
        if len(_pending_queue) >= BATCH_SIZE:
            threading.Thread(target=_flush_batch, daemon=True).start()
    
    logger.info(f"Queued for batch commit: {slug} (queue size: {len(_pending_queue)})")
    
    return public_url, {}


def publish_to_vercel_with_content(slug: str, html_content: str, screenshots: "dict | None" = None) -> str:
    """
    Crée un nouveau déploiement Vercel avec le contenu HTML.
    """
    if not VERCEL_TOKEN:
        raise Exception("VERCEL_TOKEN manquant")
    
    headers = {
        "Authorization": f"Bearer {VERCEL_TOKEN}",
        "Content-Type": "application/json"
    }
    
    files = []
    
    files.append({
        "file": f"{slug}/index.html",
        "data": html_content,
        "encoding": "utf-8"
    })
    
    if screenshots:
        for key, path in screenshots.items():
            if isinstance(path, str) and path and os.path.exists(path):
                with open(path, "rb") as img_file:
                    encoded = base64.b64encode(img_file.read()).decode('utf-8')
                files.append({
                    "file": f"{slug}/{os.path.basename(path)}",
                    "data": encoded,
                    "encoding": "base64"
                })
    
    payload = {
        "name": VERCEL_PROJECT_NAME,
        "files": files,
        "projectSettings": {
            "framework": None,
            "outputDirectory": "."
        },
        "target": "production"
    }
    
    resp = requests.post(
        "https://api.vercel.com/v13/deployments",
        headers=headers,
        json=payload,
        timeout=30
    )
    
    if resp.status_code not in [200, 201]:
        raise Exception(f"Vercel error {resp.status_code}: {resp.text}")
    
    deploy_id = resp.json().get("id")
    logger.info(f"Vercel deployment created: {deploy_id}")
    
    for _ in range(30):
        status_resp = requests.get(
            f"https://api.vercel.com/v13/deployments/{deploy_id}",
            headers=headers,
            timeout=10
        )
        status = status_resp.json().get("readyState")
        if status == "READY":
            return f"https://{AUDIT_DOMAIN}/{slug}/"
        elif status == "ERROR":
            raise Exception("Vercel deployment ERROR")
        time.sleep(2)
    
    return f"https://{AUDIT_DOMAIN}/audits/{slug}/"


def republish_to_github(slug: str, html_content: str) -> str:
    """
    Republie un rapport immédiatement sur GitHub (hors batch).
    """
    files = [{
        "slug": slug,
        "path": f"{slug}/index.html",
        "content": html_content
    }]
    
    if _commit_files(files, f"Republish: {slug}"):
        return f"https://{AUDIT_DOMAIN}/{slug}/"
    else:
        raise Exception(f"Republish failed for {slug}")


start_batch_worker()
