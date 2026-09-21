# -*- coding: utf-8 -*-
"""
services/job_tracker.py
Centralise l'état des jobs asynchrones (Audit, Envoi Emails).
"""

# État global des jobs d'audit
_audit_job = {
    'running': False,
    'logs': [],
    'returncode': None,
    'total': 0,
    'current': 0,
    'failed': 0
}

# État global des jobs d'envoi d'emails
_email_job = {
    'running': False,
    'cancelled': False,
    'total': 0,
    'current': 0,
    'success': 0,
    'failed': 0,
    'results': []
}

# État global des jobs de recherche d'emails (Enrichissement)
_enrich_job = {
    'running': False,
    'total': 0,
    'current': 0,
    'success': 0,
    'failed': 0,
    'results': []
}

def get_audit_status():
    return _audit_job

def get_email_status():
    return _email_job

def get_enrich_status():
    return _enrich_job

def reset_audit_job(total=0):
    _audit_job.update({
        'running': True,
        'logs': [],
        'returncode': None,
        'total': total,
        'current': 0,
        'failed': 0
    })

def reset_email_job(total=0):
    _email_job.update({
        'running': True,
        'cancelled': False,
        'total': total,
        'current': 0,
        'success': 0,
        'failed': 0,
        'results': []
    })

def reset_enrich_job(total=0):
    _enrich_job.update({
        'running': True,
        'total': total,
        'current': 0,
        'success': 0,
        'failed': 0,
        'results': []
    })
