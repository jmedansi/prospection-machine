# -*- coding: utf-8 -*-
"""
core/pipeline_registry.py
Registre central pour les pipelines configurables.
Permet d'enregistrer des routines métier (scraping, audit, envoi batch) de manière modulaire.
"""
import logging
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

class PipelineRegistry:
    """Registre des pipelines."""
    _pipelines: Dict[str, Dict] = {}

    @classmethod
    def register(cls, name: str, func: Callable, interval_hours: Optional[int] = 1, description: str = ""):
        """Enregistre un pipeline avec sa fréquence souhaitée."""
        cls._pipelines[name] = {
            'func': func,
            'interval': interval_hours,
            'description': description
        }
        logger.info(f"[Registry] Pipeline '{name}' enregistré (f={interval_hours}h)")

    @classmethod
    def get_all(cls) -> Dict[str, Dict]:
        """Retourne tous les pipelines enregistrés."""
        return cls._pipelines

# Instance globale
registry = PipelineRegistry()
