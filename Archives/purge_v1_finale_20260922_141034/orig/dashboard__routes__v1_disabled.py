# -*- coding: utf-8 -*-
"""
dashboard/routes/v1_disabled.py
Barrière de décommissionnement du pipeline v1 (leads_bruts / leads_audites /
email_builder / V5 archive). Toute route V1-PUR (consommée uniquement par la V5)
est remplacée par un stub HTTP 410 « décommissionné ».

Les routes SHARED (encore appelées par la production V6) ne sont PAS désactivées :
  /api/leads (GET), /api/leads/<id>/edit, /api/leads/<id>/contact,
  /api/leads/batch-delete, /api/leads/batch-classify, /api/leads/find-emails,
  /api/sources/stats, /api/audit/launch|retry-failed|status,
  /api/email/generate|send|send-approved|cancel|test|update|approve|disapprove|thread,
  /api/scraper/launch|status|stop, /api/sniper/* (sauf stops/quota), /api/planning*,
  /api/campaigns*, /api/settings/sources, /api/previews* , /api/tasks*,
  GET /api/lists, /api/stats, /api/ia/*, /resend (webhook), mailboxes/config/health/logs.
"""
from flask import jsonify

V1_MESSAGE = (
    "Cet endpoint appartient au pipeline v1 (décommissionné). "
    "Utilisez les endpoints /api/v2/* du modèle Campagne → Liste → Prospect."
)

# Endpoints <blueprint>.<fonction> considérés 100 % v1 (V5-only)
V1_PUR_ENDPOINTS = {
    # ── leads.py ──
    "leads.api_leads_all",
    "leads.api_lead_update_status",
    "leads.api_leads_sectors",
    "leads.api_leads_purge_zero_avis",
    "leads.api_lead_by_id",
    "leads.api_lead_update",
    "leads.api_lead_set_objectif",
    "leads.api_lead_set_categorie",
    "leads.api_lead_ecarter",
    "leads.api_lead_desinscrire",
    "leads.api_leads_categories",
    "leads.api_enrich_status",
    "leads.api_enrich_stop",
    "leads.api_leads_find_email",
    "leads.api_lead_delete",
    "leads.api_regenerate_email_stream",
    "leads.api_leads_import",
    # ── audits.py ──
    "audits.api_audit_stop",
    "audits.api_audit_cleanup",
    # ── emails.py (V1) ──
    "emails.api_email_status",
    "emails.api_emails_list",
    "emails.api_email_by_id",
    "emails.api_crm_update",
    "emails.api_crm_manual_contact",
    "emails.api_crm_list",
    "emails.api_crm_counts",
    "emails.api_tracking_list",
    "emails.api_sequences_list",
    "emails.api_sequences_pending",
    "emails.api_sequences_history",
    "emails.api_sequence_approve",
    "emails.api_sequences_approve_bulk",
    "emails.api_sequence_cancel",
    # ── campaigns.py (legacy planned_campaigns / planning) ──
    "campaigns.api_get_scraping_priorities",
    "campaigns.api_add_scraping_priority",
    "campaigns.api_delete_scraping_priority",
    "campaigns.api_toggle_scraping_priority",
    "campaigns.api_auto_plan_now",
    "campaigns.api_auto_plan_backlog",
    "campaigns.api_planning_add_alias",
    "campaigns.api_scraper_all_status",
    "campaigns.api_scraper_force_stop",
    "campaigns.api_collectes",
    "campaigns.api_fill_quota",
    # ── stats.py (V1) ──
    "stats.api_stats_funnel",
    "stats.api_stats_niche",
    "stats.api_stats_export",
    "stats.api_stats_ab_test",
    # ── review.py ──
    "review.pipeline_review",
    # ── sniper.py (V1-PUR) ──
    "sniper.api_sniper_bodacc_stop",
    "sniper.api_sniper_bodacc_scan_old",
    "sniper.api_sniper_quota",
    "sniper.api_sniper_stop",
    "sniper.api_sniper_force_stop",
    "sniper.api_sniper_fb_ads_stop",
    "sniper.api_sniper_ecom_stop",
    "sniper.api_sniper_jobs_stop",
    # ── templates.py (legacy) ──
    "templates.list_templates",
    "templates.get_template",
    "templates.save_template",
    "templates.preview_template",
    # ── lists.py (legacy lead_lists) ──
    "lists.api_lists_reset",
    "lists.api_lists_default_refresh",
    "lists.api_lists_create_sector_batches",
    "lists.api_lists_get_one",
    "lists.api_lists_create",
    "lists.api_lists_update",
    "lists.api_lists_delete",
    "lists.api_list_leads",
    "lists.api_list_add_leads",
    "lists.api_list_remove_leads",
    "lists.api_lead_lists",
    "lists.api_list_action",
}


def _v1_gone(*_args, **_kwargs):
    return jsonify({"error": "V1 décommissionné", "code": 410, "detail": V1_MESSAGE}), 410


def disable_v1(app):
    """Remplace les view_functions V1-PUR par un stub 410. Retourne le nb désactivé."""
    disabled = 0
    missing = []
    for name in V1_PUR_ENDPOINTS:
        if name in app.view_functions:
            app.view_functions[name] = _v1_gone
            disabled += 1
        else:
            missing.append(name)
    if missing:
        app.logger.warning("[v1_disabled] endpoints introuvables : %s", ", ".join(sorted(missing)))
    app.logger.info("[v1_disabled] %d endpoint(s) v1 désactivé(s) (410 Gone)", disabled)
    return disabled