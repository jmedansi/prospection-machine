# -*- coding: utf-8 -*-
"""
agents/scraper/agent.py — ScraperAgent

Responsabilité unique : lancer le scraping GMaps pour un mot-clé + ville,
créer la campagne en base et démarrer le sous-processus scraper/main.py.

Entrée  : keyword, city, sector, limit, min_emails, campaign_name
Sortie  : AgentResult { campaign_id, message }
"""
from __future__ import annotations
import os, sys, subprocess
from core.result import BaseAgent, AgentResult, timed
from database.repos import campaigns_repo

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class ScraperAgent(BaseAgent):
    name = "scraper"

    @timed("scraper")
    def run(self, keyword: str, city: str, sector: str = "",
            limit: int = 50, min_emails: int = 10,
            campaign_name: str = "") -> AgentResult:
        """
        Lance un scraping en arrière-plan.

        Args:
            keyword:       Mot-clé de recherche (ex: "plombier")
            city:          Ville cible (ex: "Paris")
            sector:        Secteur d'activité optionnel
            limit:         Nombre max de leads à scraper
            min_emails:    Seuil minimum d'emails valides
            campaign_name: Nom de la campagne (auto-généré si vide)

        Returns:
            AgentResult.data = { "campaign_id": int, "message": str }
        """
        if not keyword or not city:
            return self.fail("keyword et city sont requis")

        if not campaign_name:
            campaign_name = f"{sector or keyword} {city}"

        # 1. Créer la campagne en base
        camp_id = campaigns_repo.create(campaign_name, sector or keyword, city, nb_demande=limit)
        if not camp_id:
            return self.fail("Impossible de créer la campagne en base")

        # 2. Construire la commande subprocess
        pythonw = r"C:\Python314\pythonw.exe" if sys.platform == "win32" else sys.executable
        flags   = 0x08000000 if sys.platform == "win32" else 0
        cmd = [
            pythonw,
            os.path.join(ROOT, "scraper", "main.py"),
            "--keyword", keyword,
            "--city",    city,
            "--limit",   str(limit),
            "--min-emails", str(min_emails),
            "--campaign-id", str(camp_id),
        ]

        # 3. Lancer en arrière-plan
        try:
            subprocess.Popen(
                cmd, cwd=ROOT,
                creationflags=flags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            # Si pythonw n'existe pas, retry avec python
            cmd[0] = sys.executable
            subprocess.Popen(
                cmd, cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        self.logger.info(f"Scraping lancé : '{keyword}' à '{city}' — campagne #{camp_id}")
        return self.ok({
            "campaign_id": camp_id,
            "message":     f"Scraping lancé pour '{keyword}' à '{city}'",
        })


# Singleton
scraper_agent = ScraperAgent()
