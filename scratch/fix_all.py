# -*- coding: utf-8 -*-
import re
from pathlib import Path

TEMPLATES_DIR = Path("d:/prospection-machine/synthetiseur/templates_sites")
INJECT_FILE = Path("d:/prospection-machine/inject_profil_a.py")

# 1. Update inject_profil_a.py to include the CSS for the suite floue in CSS_TEMPLATE
inject_content = INJECT_FILE.read_text(encoding="utf-8")

suite_floue_css = """
/* ── NOUVELLE SECTOR PREVIEW (ULTRA PREMIUM) ── */
.section-suite-floue {
  position: relative;
  padding: 8rem 4rem 14rem;
  background: #ffffff;
  overflow: hidden;
  width: 100vw;
}
.suite-container {
  max-width: 1200px;
  margin: 0 auto;
  position: relative;
  z-index: 2;
}
.suite-subtitle {
  display: block;
  font-size: 0.8rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.2em;
  color: {accent};
  margin-bottom: 0.75rem;
  text-align: center;
}
.suite-title {
  font-family: inherit;
  font-size: clamp(2rem, 4vw, 3rem);
  font-weight: 800;
  color: #0f172a;
  text-align: center;
  margin-bottom: 4rem;
  letter-spacing: -0.02em;
}
.suite-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 2.5rem;
}
.suite-card {
  background: #f8fafc;
  border-radius: 20px;
  overflow: hidden;
  border: 1px solid rgba(15, 23, 42, 0.05);
  box-shadow: 0 4px 30px rgba(15, 23, 42, 0.02);
  transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}
.suite-card:hover {
  transform: translateY(-8px);
  box-shadow: 0 20px 40px rgba(15, 23, 42, 0.08);
}
.suite-card-img {
  height: 220px;
  background-size: cover;
  background-position: center;
  position: relative;
}
.suite-card-img::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(to bottom, transparent, rgba(15, 23, 42, 0.2));
}
.suite-card-body {
  padding: 2rem;
}
.suite-card-body h3 {
  font-size: 1.25rem;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 0.75rem;
}
.suite-card-body p {
  color: #64748b;
  font-size: 0.95rem;
  line-height: 1.6;
}

/* Overlay de flou progressif */
.suite-blur-overlay {
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
}
.suite-blur-card {
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 24px;
  padding: 3rem;
  max-width: 580px;
  text-align: center;
  box-shadow: 0 30px 60px rgba(15, 23, 42, 0.12), 0 0 100px rgba(255, 255, 255, 0.5);
  animation: suite_float 6s ease-in-out infinite;
}
@keyframes suite_float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-6px); }
}
.suite-blur-tag {
  display: inline-block;
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  color: {accent};
  margin-bottom: 1rem;
}
.suite-blur-title {
  font-size: 1.6rem;
  font-weight: 800;
  color: #0f172a;
  line-height: 1.3;
  margin-bottom: 1rem;
  letter-spacing: -0.01em;
}
.suite-blur-text {
  color: #64748b;
  font-size: 0.95rem;
  line-height: 1.6;
  margin-bottom: 2rem;
}
.suite-blur-btn {
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
}
.suite-blur-btn:hover {
  background: {accent};
  transform: translateY(-2px);
  box-shadow: 0 15px 30px rgba(15, 23, 42, 0.3);
}

@media(max-width: 768px) {
  .section-suite-floue {
    padding: 6rem 1.5rem 10rem;
    width: 100%;
  }
  .suite-blur-overlay {
    padding-bottom: 4rem;
  }
  .suite-blur-card {
    padding: 2rem 1.5rem;
  }
  .suite-grid {
    grid-template-columns: 1fr;
  }
}
"""

# Append the suite floue CSS inside CSS_TEMPLATE of inject_profil_a.py
if "/* ── NOUVELLE SECTOR PREVIEW" not in inject_content:
    # Find the end of CSS_TEMPLATE (before the closing triple quotes)
    pattern = re.compile(r'(CSS_TEMPLATE = ""\".*?)(\n\"\"\")', re.DOTALL)
    inject_content = pattern.sub(r'\1' + suite_floue_css + r'\2', inject_content)
    INJECT_FILE.write_text(inject_content, encoding="utf-8")
    print("SUCCESS: Injected suite floue CSS into inject_profil_a.py")

# 2. Fix the templates styling (nav duplicate, text overlaps, readable colors, page layouts)
for html_file in TEMPLATES_DIR.glob("**/*.html"):
    if not html_file.is_file():
        continue
    content = html_file.read_text(encoding="utf-8")
    
    # -- Fix overlap of company name and subtitle/taglines in Nav --
    # Ensure nav-brand-text doesn't wrap or overlap
    content = re.sub(
        r'\.nav-brand-text\{([^}]+)\}',
        r'.nav-brand-text{\1; display: flex; flex-direction: column; gap: 2px;}',
        content
    )
    
    # If the file has a double nav title, let's look at the nav and make it clean
    # For example, let's make sure the logo is hid and text logo class matches .nav-logo-text
    content = content.replace('class="nav-logo-text"', 'class="nav-logo-text nav-name"')
    
    # -- Make nav links readable (white with opacity for dark navs, dark for light navs) --
    # Find nav-center a or nav-links a and make them highly readable
    content = re.sub(
        r'(\.nav-links a|\.nav-center a)\s*\{([^}]+)\}',
        r'\1 {\2; color: rgba(255, 255, 255, 0.85) !important; font-weight: 600; text-shadow: 0 1px 4px rgba(0,0,0,0.5);}',
        content
    )
    
    # -- Fix spacing (text stuck to left, empty right) --
    # Increase the hero content or inner max-width to look balanced
    content = re.sub(
        r'(\.hero-inner|\.hero-content)\s*\{([^}]+)\}',
        r'\1 {\2; max-width: 800px; width: 60%;}',
        content
    )
    
    # Add a backup style just in case width is not set
    style_insert = "\n.hero-inner, .hero-content { max-width: 850px !important; width: 60% !important; z-index: 10; }\n"
    style_close_idx = content.find("</style>")
    if style_close_idx != -1:
        content = content[:style_close_idx] + style_insert + content[style_close_idx:]
        
    html_file.write_text(content, encoding="utf-8")

print("FINISHED FIXING ALL TEMPLATES")
