# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
"""
inject_profil_a.py  (v2 — corrige doublons + variables)
=========================================================
- Nettoie d'abord toute injection précédente (depuis le marqueur jusqu'à </body>)
- Supprime les anciennes sections non-préfixées dans hotellerie (preview-section, cta-box…)
- Injecte proprement le CSS + HTML profil-A avec les bonnes variables {{NOM_ENTREPRISE}}
"""

import os, re, glob

SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(SCRIPT_DIR, "synthetiseur", "templates_sites")

# Marqueur d'injection (début du bloc injecté)
INJECT_START_COMMENT = "<!-- \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\n     PROFIL A"
INJECT_CSS_COMMENT   = "/* \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\n   PROFIL A"

# Détection : fichier déjà proprement injecté (v2)
MARKER_V2 = 'class="profil-a-header"'

COLOR_RE = re.compile(r'COULEUR ACCENT.*?:\s*(#[0-9a-fA-F]{6})', re.IGNORECASE)

FALLBACK_COLORS = {
    "artisan":    "#e07b39",
    "auto":       "#e63946",
    "beaute":     "#c9a0a0",
    "bijouterie": "#d4af37",
    "commerce":   "#e76f51",
    "default":    "#3d5a80",
    "hotellerie": "#b5924c",
    "immobilier": "#1a3c34",
    "juridique":  "#1e3a5f",
    "numerique":  "#7c3aed",
    "restaurant": "#c8a96e",
    "sante":      "#0077b6",
    "sport":      "#00c896",
    "comptable":  "#1a5276",
    "education":  "#c0392b",
    "evenementiel":"#d4af37",
    "microfinance":"#1a5276",
}

# ── CSS à injecter (utilise {accent} via .format()) ───────────────────────────
CSS_TEMPLATE = """
/* ═══════════════════════════════════════════════════════════════════════════
   PROFIL A — Sections rapport Incidenx
   ═══════════════════════════════════════════════════════════════════════════ */

/* ── Correction globale hero-content / hero-inner ── */
.hero-content,
.hero-inner {{
  padding-top: 7rem !important;
  max-width: 68% !important;
  min-width: min(520px, 90vw);
  padding-left: clamp(4rem, 7vw, 8rem) !important;
  padding-right: clamp(2rem, 3vw, 4rem) !important;
}}
@media(max-width: 1200px) {{
  .hero-content,
  .hero-inner {{
    max-width: 72% !important;
    padding-left: clamp(3rem, 5vw, 5rem) !important;
  }}
}}
@media(max-width: 1024px) {{
  .hero-content,
  .hero-inner {{
    padding-top: 6rem !important;
    max-width: 78% !important;
    padding-left: 3rem !important;
    padding-right: 2rem !important;
  }}
}}
@media(max-width: 900px) {{
  .hero-content,
  .hero-inner {{
    padding-top: 5rem !important;
    max-width: 100% !important;
    width: 100% !important;
    padding-left: 1.5rem !important;
    padding-right: 1.5rem !important;
  }}
}}

/* ── Nav : flou + limites alignées avec le contenu ── */
nav {{
  padding-left: clamp(4rem, 7vw, 8rem) !important;
  padding-right: clamp(4rem, 7vw, 8rem) !important;
  background: rgba(0, 0, 0, 0.25) !important;
  backdrop-filter: blur(14px) !important;
  -webkit-backdrop-filter: blur(14px) !important;
}}
@media(max-width: 1200px) {{
  nav {{
    padding-left: clamp(3rem, 5vw, 5rem) !important;
    padding-right: clamp(3rem, 5vw, 5rem) !important;
  }}
}}
@media(max-width: 1024px) {{
  nav {{
    padding-left: 3rem !important;
    padding-right: 3rem !important;
  }}
}}
@media(max-width: 900px) {{
  nav {{
    padding-left: 1.5rem !important;
    padding-right: 1.5rem !important;
  }}
}}

/* ── Bouton téléphone — vrai bouton avec bordure ── */
.nav-tel,
a[href^="tel"].nav-tel,
a[href^="tel"].btn-tel-nav,
a[href^="tel"].nav-phone {{
  display: inline-flex !important;
  align-items: center !important;
  gap: 0.45rem !important;
  padding: 0.55rem 1.25rem !important;
  border: 1.5px solid rgba(255, 255, 255, 0.45) !important;
  border-radius: 6px !important;
  color: #ffffff !important;
  font-size: 0.75rem !important;
  font-weight: 600 !important;
  letter-spacing: 0.06em !important;
  text-decoration: none !important;
  white-space: nowrap !important;
  background: rgba(255, 255, 255, 0.08) !important;
  transition: all 0.2s ease !important;
}}
.nav-tel:hover,
a[href^="tel"].nav-tel:hover {{
  background: rgba(255, 255, 255, 0.18) !important;
  border-color: rgba(255, 255, 255, 0.75) !important;
}}

/* ── Nav logo-text toujours lisible ── */
.nav-logo-text,
.nav-name {{
  max-width: 260px !important;
  white-space: nowrap !important;
  overflow: hidden !important;
  text-overflow: ellipsis !important;
  display: block !important;
}}

.profil-a-preview-section {{
  padding: 6rem 2rem;
  max-width: 1200px;
  margin: 0 auto;
  font-family: inherit;
}}


.profil-a-info-grid {{
  display: grid;
  grid-template-columns: 1.1fr 0.9fr;
  gap: 5rem;
  align-items: center;
}}
.profil-a-info-text h2 {{
  font-family: inherit;
  font-size: clamp(2rem, 3.5vw, 2.75rem);
  font-weight: 800;
  letter-spacing: -0.03em;
  margin-bottom: 1.5rem;
  color: #0f172a;
  line-height: 1.15;
}}
.profil-a-info-text p {{
  color: #475569;
  font-size: 1.05rem;
  line-height: 1.8;
}}
.profil-a-arg-item {{
  display: flex;
  gap: 1.5rem;
  margin-bottom: 2rem;
  background: #ffffff;
  padding: 1.5rem;
  border-radius: 16px;
  box-shadow: 0 4px 20px rgba(15, 23, 42, 0.03);
  border: 1px solid rgba(15, 23, 42, 0.05);
  transition: transform 0.3s ease, box-shadow 0.3s ease;
}}
.profil-a-arg-item:hover {{
  transform: translateY(-2px);
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.06);
}}
.profil-a-arg-item:last-child {{ margin-bottom: 0; }}
.profil-a-arg-num {{
  width: 42px;
  height: 42px;
  background: rgba(15, 23, 42, 0.05);
  color: {accent};
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  font-size: 1.1rem;
  flex-shrink: 0;
  border: 1px solid rgba(15, 23, 42, 0.08);
  box-shadow: inset 0 2px 4px rgba(0,0,0,0.02);
}}
.profil-a-arg-content h3 {{
  font-family: inherit;
  font-size: 1.15rem;
  font-weight: 700;
  margin-bottom: 0.35rem;
  color: #0f172a;
}}
.profil-a-arg-content p {{
  color: #475569;
  font-size: 0.92rem;
  line-height: 1.6;
}}

.profil-a-cta-box {{
  background: linear-gradient(135deg, #0f172a 0%, #020617 100%);
  padding: 7rem 2rem;
  text-align: center;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  position: relative;
  overflow: hidden;
  font-family: inherit;
}}
.profil-a-cta-box::before {{
  content: '';
  position: absolute;
  top: -50%;
  left: -50%;
  width: 200%;
  height: 200%;
  background: radial-gradient(circle, rgba(255,255,255,0.03) 0%, transparent 70%);
  pointer-events: none;
}}
.profil-a-cta-title {{
  font-family: inherit;
  font-size: clamp(1.8rem, 3.5vw, 2.5rem);
  font-weight: 800;
  letter-spacing: -0.02em;
  margin-bottom: 1rem;
  color: #ffffff;
}}
.profil-a-cta-sub {{
  color: #94a3b8;
  margin-bottom: 3.5rem;
  max-width: 650px;
  margin-left: auto;
  margin-right: auto;
  line-height: 1.8;
  font-size: 1.05rem;
}}
.profil-a-btn {{
  display: inline-flex;
  align-items: center;
  gap: 0.75rem;
  background: {accent};
  color: #ffffff;
  padding: 1.25rem 3rem;
  border-radius: 9999px;
  text-decoration: none;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-size: 0.85rem;
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
  position: relative;
}}
.profil-a-btn:hover {{
  transform: translateY(-3px);
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
  filter: brightness(1.1);
}}
.profil-a-btn::after {{
  content: '';
  position: absolute;
  inset: -3px;
  border-radius: 9999px;
  background: {accent};
  opacity: 0.3;
  z-index: -1;
  animation: pulse-ring 2s cubic-bezier(0.215, 0.610, 0.355, 1) infinite;
}}

@keyframes pulse-ring {{
  0% {{ transform: scale(0.95); opacity: 0.5; }}
  50% {{ transform: scale(1.05); opacity: 0; }}
  100% {{ transform: scale(0.95); opacity: 0; }}
}}

.profil-a-footer {{
  background: #020617;
  color: rgba(255, 255, 255, 0.35);
  text-align: center;
  padding: 5rem 2rem 3rem;
  font-size: 0.875rem;
  border-top: 1px solid rgba(255, 255, 255, 0.03);
  font-family: inherit;
}}
.profil-a-footer a {{
  color: rgba(255, 255, 255, 0.6);
  text-decoration: none;
  font-weight: 600;
  transition: color .2s;
}}
.profil-a-footer a:hover {{ color: {accent}; }}

.footer-services-container {{
  max-width: 1200px;
  margin: 0 auto 3rem;
  padding-bottom: 3rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  text-align: left;
}}
.footer-services-title {{
  font-size: 0.9rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  color: #ffffff;
  margin-bottom: 1.5rem;
}}
.footer-services-list {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1.5rem;
  list-style: none;
  padding: 0;
}}
.footer-services-list li {{
  color: rgba(255, 255, 255, 0.5);
  font-size: 0.9rem;
  position: relative;
  padding-left: 1.25rem;
}}
.footer-services-list li::before {{
  content: '✓';
  position: absolute;
  left: 0;
  color: {accent};
  font-weight: bold;
}}

@media(max-width: 768px) {{
  .profil-a-preview-section {{ padding: 4rem 1.25rem; }}
  .profil-a-info-grid {{ grid-template-columns: 1fr; gap: 2rem; padding: 3rem 0; }}
  .profil-a-cta-box {{ padding: 5rem 1.25rem; }}
  .profil-a-btn {{ width: 100%; justify-content: center; }}
  .footer-services-list {{ grid-template-columns: 1fr; gap: 1rem; }}
}}

/* ── NOUVELLE SECTOR PREVIEW (ULTRA PREMIUM) ── */
.section-suite-floue {{
  position: relative;
  padding: 8rem 4rem 14rem;
  background: #ffffff;
  overflow: hidden;
  width: 100vw;
}}
.suite-container {{
  max-width: 1200px;
  margin: 0 auto;
  position: relative;
  z-index: 2;
}}
.suite-subtitle {{
  display: block;
  font-size: 0.8rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.2em;
  color: {accent};
  margin-bottom: 0.75rem;
  text-align: center;
}}
.suite-title {{
  font-family: inherit;
  font-size: clamp(2rem, 4vw, 3rem);
  font-weight: 800;
  color: #0f172a;
  text-align: center;
  margin-bottom: 4rem;
  letter-spacing: -0.02em;
}}
.suite-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 2.5rem;
}}
.suite-card {{
  background: #f8fafc;
  border-radius: 20px;
  overflow: hidden;
  border: 1px solid rgba(15, 23, 42, 0.05);
  box-shadow: 0 4px 30px rgba(15, 23, 42, 0.02);
  transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}}
.suite-card:hover {{
  transform: translateY(-8px);
  box-shadow: 0 20px 40px rgba(15, 23, 42, 0.08);
}}
.suite-card-img {{
  height: 220px;
  background-size: cover;
  background-position: center;
  position: relative;
}}
.suite-card-img::after {{
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(to bottom, transparent, rgba(15, 23, 42, 0.2));
}}
.suite-card-body {{
  padding: 2rem;
}}
.suite-card-body h3 {{
  font-size: 1.25rem;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 0.75rem;
}}
.suite-card-body p {{
  color: #64748b;
  font-size: 0.95rem;
  line-height: 1.6;
}}

/* Overlay de flou progressif — multi-couches */
.suite-blur-overlay {{
  position: absolute;
  inset: 0;
  z-index: 10;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding-bottom: 6rem;
  pointer-events: none;
}}
/* Couche 1 : voile blanc progressif (du transparent vers blanc) */
.suite-blur-overlay::before {{
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(to bottom, 
    rgba(255,255,255,0) 0%,
    rgba(255,255,255,0) 10%,
    rgba(255,255,255,0.6) 30%,
    rgba(255,255,255,0.96) 55%,
    #ffffff 100%
  );
  pointer-events: none;
}}
/* Couche 2 : backdrop-filter avec mask progressif pour le flou */
.suite-blur-layer {{
  position: absolute;
  inset: 0;
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  -webkit-mask-image: linear-gradient(to bottom, transparent 0%, transparent 15%, black 45%, black 100%);
  mask-image: linear-gradient(to bottom, transparent 0%, transparent 15%, black 45%, black 100%);
  pointer-events: none;
}}
/* La carte CTA au dessus des couches */
.suite-blur-overlay > .suite-blur-card {{
  pointer-events: auto;
  position: relative;
  z-index: 5;
}}
.suite-blur-card {{
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 24px;
  padding: 3rem;
  max-width: 580px;
  text-align: center;
  box-shadow: 0 30px 60px rgba(15, 23, 42, 0.12), 0 0 100px rgba(255, 255, 255, 0.5);
  animation: suite_float 6s ease-in-out infinite;
}}
@keyframes suite_float {{
  0%, 100% {{ transform: translateY(0); }}
  50% {{ transform: translateY(-6px); }}
}}
.suite-blur-tag {{
  display: inline-block;
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  color: {accent};
  margin-bottom: 1rem;
}}
.suite-blur-title {{
  font-size: 1.6rem;
  font-weight: 800;
  color: #0f172a;
  line-height: 1.3;
  margin-bottom: 1rem;
  letter-spacing: -0.01em;
}}
.suite-blur-text {{
  color: #64748b;
  font-size: 0.95rem;
  line-height: 1.6;
  margin-bottom: 2rem;
}}
.suite-blur-btn {{
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  background: #0f172a;
  color: #ffffff;
  padding: 1.1rem 2.5rem;
  border-radius: 9999px;
  text-decoration: none;
  font-weight: 700;
  font-size: 0.9rem;
  transition: all 0.3s ease;
  box-shadow: 0 10px 25px rgba(15, 23, 42, 0.2);
}}
.suite-blur-btn:hover {{
  background: {accent};
  transform: translateY(-2px);
  box-shadow: 0 15px 30px rgba(15, 23, 42, 0.3);
}}

@media(max-width: 768px) {{
  .section-suite-floue {{
    padding: 6rem 1.5rem 10rem;
    width: 100%;
  }}
  .suite-blur-overlay {{
    padding-bottom: 4rem;
  }}
  .suite-blur-card {{
    padding: 2rem 1.5rem;
  }}
  .suite-grid {{
    grid-template-columns: 1fr;
  }}
}}
"""

# ── HTML à injecter — variables {{VARIABLE}} = syntaxe Python replace, {% %} = Jinja2
# NB: ce bloc est une chaîne brute, PAS passée dans .format()
HTML_BLOCK = """

<!-- =====================================================================
     PROFIL A — Sections rapport Incidenx (inject_profil_a.py v2)
     ===================================================================== -->

<!-- Section arguments -->
<section class="profil-a-preview-section">
  <div class="profil-a-info-grid">
    <div class="profil-a-info-text">
      <h2>Pourquoi votre entreprise m\u00e9rite cette pr\u00e9sence.</h2>
      <p>Aujourd'hui, 82% des clients \u00e0 {{VILLE}} effectuent une recherche Google avant de choisir un professionnel. \u00catre invisible, c'est laisser le champ libre \u00e0 vos concurrents.</p>
    </div>
    <div class="profil-a-info-args">
      <div class="profil-a-arg-item">
        <div class="profil-a-arg-num">1</div>
        <div class="profil-a-arg-content">
          <h3>Cr\u00e9dibilit\u00e9 imm\u00e9diate</h3>
          <p>Une pr\u00e9sence web soign\u00e9e transforme un prospect h\u00e9sitant en client convaincu.</p>
        </div>
      </div>
      <div class="profil-a-arg-item">
        <div class="profil-a-arg-num">2</div>
        <div class="profil-a-arg-content">
          <h3>Capture mobile 24/7</h3>
          <p>Votre futur site est optimis\u00e9 pour transformer chaque clic sur smartphone en appel direct.</p>
        </div>
      </div>
      <div class="profil-a-arg-item">
        <div class="profil-a-arg-num">3</div>
        <div class="profil-a-arg-content">
          <h3>Expansion locale</h3>
          <p>Attirez des clients au-del\u00e0 de votre quartier gr\u00e2ce \u00e0 un r\u00e9f\u00e9rencement Google Maps ma\u00eetris\u00e9.</p>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- CTA -->
<section class="profil-a-cta-box">
  <div class="profil-a-cta-title">Ce site peut \u00eatre en ligne dans 3 semaines.</div>
  <p class="profil-a-cta-sub">
    Nous avons d\u00e9j\u00e0 pr\u00e9par\u00e9 toute la structure technique. Il ne manque plus que votre feu vert pour finaliser les contenus.
  </p>
  <a href="https://calendly.com/jmedansi/15min" class="profil-a-btn">
    Prendre 15 min pour en discuter \u2794
  </a>
</section>

<!-- Footer Incidenx -->
<footer class="profil-a-footer">
  <div class="footer-services-container">
    <div class="footer-services-title">Nos expertises & prestations</div>
    <ul class="footer-services-list">
      <li>Cr\u00e9ation de site internet</li>
      <li>Optimisation Google Maps</li>
      <li>E-r\u00e9putation & Avis clients</li>
      <li>Cr\u00e9ation d'application web</li>
      <li>Visibilit\u00e9 locale & SEO</li>
    </ul>
  </div>
  <div>
    Confidentiel &middot; Proposition r\u00e9alis\u00e9e par l'\u00e9quipe d'IncidenX &middot; 2026
  </div>
</footer>
"""

# ── Patterns vieux contenu à supprimer (hotellerie et autres ayant l'ancienne version) ──
# On supprime les blocs qui commençaient dans l'ancienne version du template hotellerie
OLD_SECTIONS_RE = re.compile(
    r'\n*<div class="page-preview">.*?</div>\s*</div>\s*(?=</body>|\Z)',
    re.DOTALL
)










# ── Fonctions ──────────────────────────────────────────────────────────────────

def strip_old_injection(content: str) -> str:
    """Supprime toute injection précédente (CSS et HTML) liée au Profil A."""
    # 1. Nettoyer le CSS injecté. On cherche la balise style et on vire les blocs commentés Profil A
    # Les commentaires CSS pour profil A commencent par "/* ====" ou "/* ══" et contiennent "PROFIL A"
    # On peut faire une regex robuste pour trouver les blocs CSS de profil A
    css_block_pattern = re.compile(
        r'/\*\s*[=\u2550]+\s*PROFIL A.*?\*/.*?(?=\n\s*</style>|\Z)',
        re.DOTALL
    )
    content = css_block_pattern.sub('', content)

    # 2. Nettoyer le HTML injecté.
    # Les commentaires HTML commencent par "<!-- ===" ou "<!-- ══" et contiennent "PROFIL A"
    # On veut supprimer tout depuis ce commentaire jusqu'à la fin ou avant </body>
    html_block_pattern = re.compile(
        r'<!--\s*[=\u2550]+\s*PROFIL A.*?-->.*?(?=</body>|\Z)',
        re.DOTALL
    )
    content = html_block_pattern.sub('', content)

    return content



def strip_old_hotellerie_sections(content: str) -> str:
    """Supprime les anciennes sections profil-A non préfixées (cas hotellerie v1)."""
    match = OLD_SECTIONS_RE.search(content)
    if match:
        content = content[:match.start()] + "\n" + content[match.end():]
    return content


def detect_color(content: str, sector: str) -> str:
    m = COLOR_RE.search(content)
    if m:
        return m.group(1)
    return FALLBACK_COLORS.get(sector, "#10b981")


def inject(content: str, accent: str) -> str:
    """Injecte le CSS puis le HTML proprement."""
    # CSS — avant la fermeture </style>
    css_block = "\n" + CSS_TEMPLATE.format(accent=accent) + "\n"
    style_close_idx = content.rfind("</style>")
    if style_close_idx == -1:
        content = content.replace("<head>", "<head>\n<style>" + css_block + "</style>", 1)
    else:
        content = content[:style_close_idx] + css_block + content[style_close_idx:]

    # HTML — formater l'accent dans le bloc HTML et l'insérer juste avant </body>
    formatted_html_block = HTML_BLOCK.replace("{accent}", accent)
    body_close_idx = content.rfind("</body>")
    if body_close_idx == -1:
        content += formatted_html_block
    else:
        content = content[:body_close_idx] + formatted_html_block + content[body_close_idx:]

    return content



def process_file(filepath: str) -> str:
    """Nettoie + réinjecte. Retourne 'ok', 'skip' ou 'err'."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"  [ERR] lecture : {e}")
        return "err"

    # Nettoyage injection précédente
    content = strip_old_injection(content)

    # Nettoyage anciennes sections non-préfixées (hotellerie v1)
    content = strip_old_hotellerie_sections(content)

    # Détecte secteur
    parts = filepath.replace("\\", "/").split("/")
    sector = "default"
    for part in reversed(parts[:-1]):
        if part in FALLBACK_COLORS:
            sector = part
            break

    accent = detect_color(content, sector)
    updated = inject(content, accent)

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(updated)
    except Exception as e:
        print(f"  [ERR] ecriture : {e}")
        return "err"

    print(f"  [OK] [{accent}]  {os.path.basename(filepath)}")
    return "ok"


def main():
    print("=" * 62)
    print("  inject_profil_a.py v2 — Nettoyage + Injection Profil A")
    print("=" * 62)
    print(f"  Repertoire : {TEMPLATES_DIR}\n")

    pattern = os.path.join(TEMPLATES_DIR, "**", "*.html")
    files = glob.glob(pattern, recursive=True)

    if not files:
        print("  [!] Aucun fichier HTML trouve !")
        return

    ok = err = 0
    prev_sector = None

    for filepath in sorted(files):
        rel = os.path.relpath(filepath, TEMPLATES_DIR)
        sector_name = rel.split(os.sep)[0].upper()
        if sector_name != prev_sector:
            print(f"\n[{sector_name}]")
            prev_sector = sector_name

        result = process_file(filepath)
        if result == "ok":
            ok += 1
        else:
            err += 1

    print("\n" + "=" * 62)
    print(f"  RESULTAT : {ok} traites, {err} erreur(s)")
    print("=" * 62)


if __name__ == "__main__":
    main()
