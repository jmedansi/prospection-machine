# -*- coding: utf-8 -*-
"""
Script de nettoyage pour les anciens rapports et fichiers temporaires
"""
import os
import shutil
from pathlib import Path
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Répertoires à nettoyer
REPORT_DIRS = [
    "reporter/reports",
    "mockups/screenshots",
    "tmp"
]

# Âge maximum des fichiers en jours
MAX_AGE_DAYS = 30

def cleanup_directory(directory: Path, max_age_days: int = MAX_AGE_DAYS):
    """Nettoie un répertoire des fichiers plus vieux que max_age_days"""
    if not directory.exists():
        logger.warning(f"Directory {directory} does not exist, skipping")
        return
    
    cutoff_time = datetime.now() - timedelta(days=max_age_days)
    deleted_count = 0
    total_size = 0
    
    for item in directory.rglob("*"):
        if item.is_file():
            # Vérifier l'âge du fichier
            file_time = datetime.fromtimestamp(item.stat().st_mtime)
            if file_time < cutoff_time:
                try:
                    file_size = item.stat().st_size
                    item.unlink()
                    deleted_count += 1
                    total_size += file_size
                    logger.debug(f"Deleted: {item} ({file_size} bytes)")
                except Exception as e:
                    logger.error(f"Error deleting {item}: {e}")
    
    if deleted_count > 0:
        logger.info(f"Cleaned {directory}: {deleted_count} files deleted, {total_size / (1024*1024):.2f} MB freed")
    else:
        logger.info(f"Cleaned {directory}: No old files found")

def cleanup_empty_directories(directory: Path):
    """Supprime les répertoires vides"""
    for item in directory.rglob("*"):
        if item.is_dir() and not any(item.iterdir()):
            try:
                item.rmdir()
                logger.debug(f"Removed empty directory: {item}")
            except Exception as e:
                logger.error(f"Error removing empty directory {item}: {e}")

def main():
    """Fonction principale de nettoyage"""
    logger.info("Starting cleanup of old reports and temporary files...")
    
    base_dir = Path(__file__).parent
    
    for dir_name in REPORT_DIRS:
        dir_path = base_dir / dir_name
        cleanup_directory(dir_path)
        cleanup_empty_directories(dir_path)
    
    # Nettoyer spécifiquement les fichiers de logs anciens
    log_files = list(base_dir.glob("*.log")) + list(base_dir.glob("*/*.log"))
    cutoff_time = datetime.now() - timedelta(days=MAX_AGE_DAYS)
    
    for log_file in log_files:
        try:
            file_time = datetime.fromtimestamp(log_file.stat().st_mtime)
            if file_time < cutoff_time:
                # Au lieu de supprimer, on fait un truncate pour garder le fichier mais vider son contenu
                with open(log_file, 'w') as f:
                    f.write('')
                logger.info(f"Truncated old log file: {log_file}")
        except Exception as e:
            logger.error(f"Error processing log file {log_file}: {e}")
    
    logger.info("Cleanup completed.")

if __name__ == "__main__":
    main()