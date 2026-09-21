# -*- coding: utf-8 -*-
"""
database/objectifs.py — SHIM de compatibilité « objectif → campagne ».

Redirige les appels historiques vers database/campagnes.py. Le module sera
supprimé une fois tous les appelants migrés (objectif_registry, orchestration,
sequence_engine, gateway, tests).
"""
from .campagnes import (  # noqa: F401
    get_auto_send_enabled,
    set_auto_send_enabled,
    create_campagne as create_objectif,
    get_campagne as get_objectif,
    get_campagne_by_nom as get_objectif_by_nom,
    list_campagnes as list_objectifs,
    update_campagne as update_objectif,
    delete_campagne as delete_objectif,
)

__all__ = [
    'get_auto_send_enabled', 'set_auto_send_enabled',
    'create_objectif', 'get_objectif', 'get_objectif_by_nom',
    'list_objectifs', 'update_objectif', 'delete_objectif',
]