# -*- coding: utf-8 -*-
import re
from pathlib import Path

file_path = Path("d:/prospection-machine/inject_profil_a.py")
content = file_path.read_text(encoding="utf-8")

# Let's clean up any previous failed injection of CSS_TEMPLATE in content
# We will restore to a clean version of CSS_TEMPLATE first

clean_css_template = """CSS_TEMPLATE = \"\"\"
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

/* Overlay de flou progressif */
.suite-blur-overlay {{
  position: absolute;
  inset: 0;
  background: linear-gradient(to bottom, 
    rgba(255, 255, 255, 0) 0%, 
    rgba(255, 255, 255, 0.3) 15%, 
    rgba(255, 255, 255, 0.85) 45%, 
    #ffffff 70%
  );
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding-bottom: 6rem;
  z-index: 10;
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
\"\"\""""

pattern = re.compile(r'CSS_TEMPLATE\s*=\s*""".*?"""', re.DOTALL)
content = pattern.sub(clean_css_template, content, count=1)
file_path.write_text(content, encoding="utf-8")
print("SUCCESS: Fixed CSS_TEMPLATE inside inject_profil_a.py")
