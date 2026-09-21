# -*- coding: utf-8 -*-
"""
dashboard/socketio_events.py — Émetteur d'événements WebSocket

Usage:
    from dashboard.socketio_events import emit_progress, emit_notification
    
    emit_progress(campaign_id=1, progress=50, leads=25)
    emit_notification(type="error", message="Campaign failed")
"""
from dashboard.app import socketio

def emit_progress(campaign_id: int = None, progress: int = 0, leads: int = 0, message: str = ""):
    """Émet un événement de progression pour le UI temps réel."""
    socketio.emit('progress', {
        'campaign_id': campaign_id,
        'progress': progress,
        'leads': leads,
        'message': message
    })

def emit_notification(notif_type: str, message: str, source: str = "system"):
    """Émet une notification en temps réel."""
    socketio.emit('notification', {
        'type': notif_type,
        'message': message,
        'source': source
    })

def emit_campaign_update(campaign_id: int, status: str, data: dict = None):
    """Émet une mise à jour de campagne."""
    socketio.emit('campaign_update', {
        'campaign_id': campaign_id,
        'status': status,
        'data': data or {}
    })