# -*- coding: utf-8 -*-
"""
agents/ — Nœuds du pipeline de prospection Incidenx

Chaque agent a une responsabilité unique et retourne un AgentResult.

Pipeline :
    ScraperAgent → EnrichisseurAgent → AuditeurAgent → ÉditeurAgent
    → PublieurAgent → RédacteurAgent → ExpéditeurAgent → TrackerAgent

Import rapide :
    from agents.scraper     import scraper_agent
    from agents.auditeur    import auditeur_agent
    from agents.redacteur   import redacteur_agent
    from agents.expediteur  import expediteur_agent
    from agents.tracker     import tracker_agent
"""
