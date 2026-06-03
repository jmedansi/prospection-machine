# -*- coding: utf-8 -*-
"""
database package — Centralise l'accès à la base de données SQLite.
"""

from .connection import get_conn, DB_PATH, logger, _serialize_json, _deserialize_json
from .schema import init_db, migrate_db
from .leads import (
    insert_lead, get_leads_pending, get_all_leads, update_lead_statut,
    get_lead_by_name, get_lead_by_id, delete_lead, update_lead,
    transition_statut, VALID_TRANSITIONS
)
from .audits import (
    insert_audit, get_audits_ready_for_email, get_audits_with_reports,
    update_audit_email, update_audit_approval, update_audit_email_content,
    update_audit_pdf
)
from .emails import insert_email_sent, update_email_tracking, insert_email_event
from .campaigns import (
    insert_campaign, get_all_campaigns, get_campaign_by_id, delete_campaign
)
from .stats import (
    get_dashboard_stats, get_leads_for_dashboard,
    get_niche_performance, get_ab_test_performance
)
from .crm import update_crm_manual, get_crm_counts, get_crm_data
from .sync import log_sync

__all__ = [
    'get_conn', 'DB_PATH', 'logger', '_serialize_json', '_deserialize_json',
    'init_db', 'migrate_db',
    'insert_lead', 'get_leads_pending', 'get_all_leads', 'update_lead_statut',
    'get_lead_by_name', 'get_lead_by_id', 'delete_lead', 'update_lead',
    'transition_statut', 'VALID_TRANSITIONS',
    'insert_audit', 'get_audits_ready_for_email', 'get_audits_with_reports',
    'update_audit_email', 'update_audit_approval', 'update_audit_email_content',
    'update_audit_pdf',
    'insert_email_sent', 'update_email_tracking', 'insert_email_event',
    'insert_campaign', 'get_all_campaigns', 'get_campaign_by_id', 'delete_campaign',
    'get_dashboard_stats', 'get_leads_for_dashboard',
    'get_niche_performance', 'get_ab_test_performance',
    'update_crm_manual', 'get_crm_counts', 'get_crm_data',
    'log_sync'
]
