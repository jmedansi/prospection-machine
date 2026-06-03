# -*- coding: utf-8 -*-
"""
dashboard/pipeline/
Package de gestion automatisée du flux de prospection.
"""
from .batch_management import maintain_batch_slots
from .approval import notify_new_audits, auto_approve_after_timeout
from .scraper_loop import start_background_scraper
from .email_generation import generate_email_for_lead

__all__ = [
    'maintain_batch_slots',
    'notify_new_audits',
    'auto_approve_after_timeout',
    'start_background_scraper',
    'generate_email_for_lead'
]
