# -*- coding: utf-8 -*-
"""
database/repos — Repositories (pattern accès données)

Importer les singletons :
    from database.repos import leads_repo, audits_repo, emails_repo, campaigns_repo
"""
from .leads_repo     import leads_repo,     LeadsRepo
from .audits_repo    import audits_repo,    AuditsRepo
from .emails_repo    import emails_repo,    EmailsRepo
from .campaigns_repo import campaigns_repo, CampaignsRepo

__all__ = [
    "leads_repo", "LeadsRepo",
    "audits_repo", "AuditsRepo",
    "emails_repo", "EmailsRepo",
    "campaigns_repo", "CampaignsRepo",
]