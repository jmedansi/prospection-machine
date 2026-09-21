# -*- coding: utf-8 -*-
"""
modules/review_machine/__init__.py
Stub minimal pour démontrer le système de plugins.
S'enregistre automatiquement au chargement.
"""
import logging
from core.pipeline_registry import registry
from database.schema import register_schema

logger = logging.getLogger(__name__)

# 1. Enregistrement du schéma (Phase 4.2)
REVIEWS_SCHEMA = """
CREATE TABLE IF NOT EXISTS review_machine_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT DEFAULT (datetime('now', 'localtime')),
    leads_processed INTEGER DEFAULT 0
);
"""

def init_module():
    """Initialise le module, crée les tables et enregistre les pipelines."""
    register_schema("Review Machine", REVIEWS_SCHEMA)
    
    # 2. Enregistrement du pipeline (Phase 4.2)
    def review_machine_pipeline():
        logger.info("[MODULE-ReviewMachine] Execution du pipeline stub")
        # Logique fictive: compter les leads sans avis Google
        pass
        
    registry.register("Review Collector", review_machine_pipeline, interval_hours=2, description="Collecte les nouveaux avis Google")
    logger.info("[MODULE-ReviewMachine] Stub initialisé")

# Appel lors de l'import
init_module()
