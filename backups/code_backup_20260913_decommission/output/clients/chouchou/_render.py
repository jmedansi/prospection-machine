# -*- coding: utf-8 -*-
"""Rend la maquette Chouchou depuis le vrai systeme de templates (synthetiseur/templates_sites)."""
import re
import jinja2
from pathlib import Path

ROOT = Path(r"D:\prospection-machine")
TPL = ROOT / "synthetiseur" / "templates_sites" / "restaurant" / "restaurant-hero-2-chaleureux.html"
assert TPL.exists(), TPL

lead = {
    "NOM_ENTREPRISE": "Chouchou",
    "VILLE": "Paris",
    "TELEPHONE": "01 45 08 02 03",
    "ADRESSE": "",
    "RATING": "4.7",
    "NB_AVIS": "828",
}

loader = jinja2.FileSystemLoader(str(TPL.parent))
env = jinja2.Environment(loader=loader, autoescape=False)
html = env.get_template(TPL.name).render(lead)

# Fallback pipeline : tout placeholder restant -> '--'
html = re.sub(r"\{\{[A-Z0-9_]+\}\}", "--", html)

out_site = ROOT / "output" / "clients" / "chouchou" / "site" / "index.html"
out_prod = ROOT / "ia_echanges" / "Restaurant Paris (auto)" / "PROMPT" / "5" / "index.html"
out_site.parent.mkdir(parents=True, exist_ok=True)
out_prod.parent.mkdir(parents=True, exist_ok=True)
out_site.write_text(html, encoding="utf-8")
out_prod.write_text(html, encoding="utf-8")
print("OK ->", out_site)
print("OK ->", out_prod)