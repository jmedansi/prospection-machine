# -*- coding: utf-8 -*-
import re
from pathlib import Path

file_path = Path("d:/prospection-machine/inject_profil_a.py")
content = file_path.read_text(encoding="utf-8")

new_css_template = """CSS_TEMPLATE = \"\"\"
/* ═══════════════════════════════════════════════════════════════════════════
   PROFIL A — Sections rapport Incidenx
   ═══════════════════════════════════════════════════════════════════════════ */

.profil-a-header {{
  background: rgba(13, 17, 23, 0.85);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  padding: 1rem 2.5rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  position: sticky;
  top: 0;
  z-index: 500;
  box-shadow: 0 4px 30px rgba(0, 0, 0, 0.03), 0 1px 0 rgba(255, 255, 255, 0.08);
}}
.profil-a-brand {{
  font-family: system-ui, -apple-system, sans-serif;
  font-size: 1.15rem;
  font-weight: 800;
  color: #fff;
  text-decoration: none;
  letter-spacing: -0.02em;
  display: flex;
  align-items: center;
}}
.profil-a-brand span {{ 
  color: {accent}; 
  text-shadow: 0 0 12px {accent};
}}
.profil-a-header-date {{
  font-family: system-ui, -apple-system, sans-serif;
  font-size: 0.72rem;
  color: rgba(255, 255, 255, 0.5);
  text-transform: uppercase;
  letter-spacing: 0.15em;
  font-weight: 600;
}}

.profil-a-preview-section {{
  padding: 6rem 2rem;
  max-width: 1200px;
  margin: 0 auto;
}}

.profil-a-info-grid {{
  display: grid;
  grid-template-columns: 1.1fr 0.9fr;
  gap: 5rem;
  align-items: center;
}}
.profil-a-info-text h2 {{
  font-family: system-ui, -apple-system, sans-serif;
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
  font-family: system-ui, -apple-system, sans-serif;
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
  font-family: system-ui, -apple-system, sans-serif;
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
  padding: 3rem;
  font-size: 0.875rem;
  border-top: 1px solid rgba(255, 255, 255, 0.03);
}}
.profil-a-footer a {{
  color: rgba(255, 255, 255, 0.6);
  text-decoration: none;
  font-weight: 600;
  transition: color .2s;
}}
.profil-a-footer a:hover {{ color: {accent}; }}

@media(max-width: 768px) {{
  .profil-a-header {{ padding: 1rem 1.5rem; }}
  .profil-a-header-date {{ display: none; }}
  .profil-a-preview-section {{ padding: 4rem 1.25rem; }}
  .profil-a-info-grid {{ grid-template-columns: 1fr; gap: 2rem; padding: 3rem 0; }}
  .profil-a-cta-box {{ padding: 5rem 1.25rem; }}
  .profil-a-btn {{ width: 100%; justify-content: center; }}
}}
\"\"\""""

new_html_block = """HTML_BLOCK = \"\"\"

<!-- =====================================================================
     PROFIL A — Sections rapport Incidenx (inject_profil_a.py v2)
     ===================================================================== -->

<!-- Header sticky Incidenx -->
<header class="profil-a-header">
  <div style="display:flex;align-items:center;gap:1.25rem">
    <a href="https://incidenx.com" class="profil-a-brand">Incidenx<span>.</span></a>
    {% if LOGO_URL %}
      <div style="height:24px;width:1px;background:rgba(255,255,255,.2)"></div>
      <img src="{{LOGO_URL}}" style="height:24px;width:auto;object-fit:contain" alt="{{NOM_ENTREPRISE}}">
    {% endif %}
  </div>
  <div class="profil-a-header-date">Proposition — {{NOM_ENTREPRISE}}</div>
</header>

<!-- Section arguments -->
<section class="profil-a-preview-section">
  <div class="profil-a-info-grid">
    <div class="profil-a-info-text">
      <h2>Pourquoi votre entreprise m\\u00e9rite cette pr\\u00e9sence.</h2>
      <p>Aujourd'hui, 82% des clients \\u00e0 {{VILLE}} effectuent une recherche Google avant de choisir un professionnel. \\u00catre invisible, c'est laisser le champ libre \\u00e0 vos concurrents.</p>
    </div>
    <div class="profil-a-info-args">
      <div class="profil-a-arg-item">
        <div class="profil-a-arg-num">1</div>
        <div class="profil-a-arg-content">
          <h3>Cr\\u00e9dibilit\\u00e9 imm\\u00e9diate</h3>
          <p>Une pr\\u00e9sence web soign\\u00e9e transforme un prospect h\\u00e9sitant en client convaincu.</p>
        </div>
      </div>
      <div class="profil-a-arg-item">
        <div class="profil-a-arg-num">2</div>
        <div class="profil-a-arg-content">
          <h3>Capture mobile 24/7</h3>
          <p>Votre futur site est optimis\\u00e9 pour transformer chaque clic sur smartphone en appel direct.</p>
        </div>
      </div>
      <div class="profil-a-arg-item">
        <div class="profil-a-arg-num">3</div>
        <div class="profil-a-arg-content">
          <h3>Expansion locale</h3>
          <p>Attirez des clients au-del\\u00e0 de votre quartier gr\\u00e2ce \\u00e0 un r\\u00e9f\\u00e9rencement Google Maps ma\\u00eetris\\u00e9.</p>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- CTA -->
<section class="profil-a-cta-box">
  <div class="profil-a-cta-title">Ce site peut \\u00eatre en ligne dans 3 semaines.</div>
  <p class="profil-a-cta-sub">
    Nous avons d\\u00e9j\\u00e0 pr\\u00e9par\\u00e9 toute la structure technique. Il ne manque plus que votre feu vert pour finaliser les contenus.
  </p>
  <a href="https://calendly.com/jmedansi/15min" class="profil-a-btn">
    Prendre 15 min avec Jean-Marc \\u2794
  </a>
</section>

<!-- Footer Incidenx -->
<footer class="profil-a-footer">
  Confidentiel &middot; Proposition r\\u00e9alis\\u00e9e par
  <a href="https://incidenx.com">Jean-Marc DANSI &middot; Incidenx</a> &middot; 2026
</footer>
\"\"\""""

# Replaces CSS_TEMPLATE in content
pattern_css = re.compile(r'CSS_TEMPLATE\s*=\s*""".*?"""', re.DOTALL)
content = pattern_css.sub(new_css_template.replace("\\", "\\\\"), content, count=1)

# Replaces HTML_BLOCK in content
pattern_html = re.compile(r'HTML_BLOCK\s*=\s*""".*?"""', re.DOTALL)
content = pattern_html.sub(new_html_block.replace("\\", "\\\\"), content, count=1)

file_path.write_text(content, encoding="utf-8")
print("SUCCESSFULLY UPDATED inject_profil_a.py")
