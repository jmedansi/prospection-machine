#!/usr/bin/env python3
"""Apply dual nav changes to all 12 hero-2 templates — v2 (cleaner)."""

import re
import os

BASE = r"D:\prospection-machine\synthetiseur\templates_sites"

FILES = {
    "restaurant/restaurant-hero-2-chaleureux.html": {
        "accent": "#d4822a",
        "font_line": '<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;0,900;1,400;1,700&family=Lato:wght@300;400;700&display=swap" rel="stylesheet">',
        "desktop_links": """          <li><a href="#">La carte</a></li>
          <li><a href="#">Notre histoire</a></li>
          <li><a href="#">Contact</a></li>""",
        "mobile_links": """          <li><a href="#">Accueil</a></li>
          <li><a href="#">Services</a></li>
          <li><a href="#">Contact</a></li>
          <li><a href="tel:{{TELEPHONE}}" class="nav-cta-mobile">Appeler</a></li>""",
        "extra_desktop": "",
        "layout": "overlay",
    },
    "sante/sante-hero-2-lumineux.html": {
        "accent": "#00b4d8",
        "font_line": '<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=Plus+Jakarta+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">',
        "desktop_links": """          <li><a href="#">Spécialités</a></li>
          <li><a href="#">L'équipe</a></li>
          <li><a href="#">Tarifs</a></li>
          <li><a href="#">Contact</a></li>""",
        "mobile_links": """          <li><a href="#">Accueil</a></li>
          <li><a href="#">Services</a></li>
          <li><a href="#">Contact</a></li>
          <li><a href="tel:{{TELEPHONE}}" class="nav-cta-mobile">Appeler</a></li>""",
        "extra_desktop": """
        <div class="nav-right">
          <span class="nav-tel-text">{{TELEPHONE}}</span>
          <a href="#" class="nav-btn">Prendre RDV</a>
        </div>""",
        "layout": "overlay",
    },
    "immobilier/immobilier-hero-2-moderne.html": {
        "accent": "#e07a5f",
        "font_line": '<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=Lora:ital,wght@0,400;1,400&display=swap" rel="stylesheet">',
        "desktop_links": """          <li><a href="#">Acheter</a></li>
          <li><a href="#">Vendre</a></li>
          <li><a href="#">Estimer</a></li>
          <li><a href="#">Contact</a></li>""",
        "mobile_links": """          <li><a href="#">Accueil</a></li>
          <li><a href="#">Services</a></li>
          <li><a href="#">Contact</a></li>
          <li><a href="tel:{{TELEPHONE}}" class="nav-cta-mobile">Appeler</a></li>""",
        "extra_desktop": "",
        "layout": "grid",
    },
    "bijouterie/bijouterie-hero-2-tendance.html": {
        "accent": "#c77dff",
        "font_line": '<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;0,900;1,400&family=Outfit:wght@300;400;500;600&display=swap" rel="stylesheet">',
        "desktop_links": """          <li><a href="#">Collections</a></li>
          <li><a href="#">Sur mesure</a></li>
          <li><a href="#">À propos</a></li>
          <li><a href="#">Contact</a></li>""",
        "mobile_links": """          <li><a href="#">Accueil</a></li>
          <li><a href="#">Services</a></li>
          <li><a href="#">Contact</a></li>
          <li><a href="tel:{{TELEPHONE}}" class="nav-cta-mobile">Appeler</a></li>""",
        "extra_desktop": """
        <a href="tel:{{TELEPHONE}}" class="nav-cta">📞 {{TELEPHONE}}</a>""",
        "layout": "overlay",
    },
    "beaute/beaute-hero-2-moderne.html": {
        "accent": "#f4a261",
        "font_line": '<link href="https://fonts.googleapis.com/css2?family=Anton&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">',
        "desktop_links": """          <li><a href="#">Services</a></li>
          <li><a href="#">Équipe</a></li>
          <li><a href="#">Tarifs</a></li>""",
        "mobile_links": """          <li><a href="#">Accueil</a></li>
          <li><a href="#">Services</a></li>
          <li><a href="#">Contact</a></li>
          <li><a href="tel:{{TELEPHONE}}" class="nav-cta-mobile">Appeler</a></li>""",
        "extra_desktop": """
        <a href="#" class="nav-btn">Book now</a>""",
        "layout": "inverted",
    },
    "commerce/commerce-hero-2-artisan.html": {
        "accent": "#2a9d8f",
        "font_line": '<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;1,400&family=Outfit:wght@300;400;500;600&display=swap" rel="stylesheet">',
        "desktop_links": """          <li><a href="#">Produits</a></li>
          <li><a href="#">À propos</a></li>
          <li><a href="#">Horaires</a></li>
          <li><a href="#">Contact</a></li>""",
        "mobile_links": """          <li><a href="#">Accueil</a></li>
          <li><a href="#">Services</a></li>
          <li><a href="#">Contact</a></li>
          <li><a href="tel:{{TELEPHONE}}" class="nav-cta-mobile">Appeler</a></li>""",
        "extra_desktop": """
        <a href="tel:{{TELEPHONE}}" class="nav-cta">📞 {{TELEPHONE}}</a>""",
        "layout": "overlay",
    },
    "juridique/juridique-hero-2-moderne.html": {
        "accent": "#2d6a4f",
        "font_line": '<link href="https://fonts.googleapis.com/css2?family=Libre+Baskerville:ital,wght@0,400;0,700;1,400&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">',
        "desktop_links": """          <li><a href="#">Expertises</a></li>
          <li><a href="#">Le cabinet</a></li>
          <li><a href="#">Tarifs</a></li>
          <li><a href="#">Contact</a></li>""",
        "mobile_links": """          <li><a href="#">Accueil</a></li>
          <li><a href="#">Services</a></li>
          <li><a href="#">Contact</a></li>
          <li><a href="tel:{{TELEPHONE}}" class="nav-cta-mobile">Appeler</a></li>""",
        "extra_desktop": """
        <a href="#" class="nav-cta">Prendre RDV</a>""",
        "layout": "overlay",
    },
    "hotellerie/hotellerie-hero-2-urbain.html": {
        "accent": "#e9c46a",
        "font_line": '<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=Inter:wght@300;400;500&display=swap" rel="stylesheet">',
        "desktop_links": """          <li><a href="#">Chambres</a></li>
          <li><a href="#">Services</a></li>
          <li><a href="#">Contact</a></li>""",
        "mobile_links": """          <li><a href="#">Accueil</a></li>
          <li><a href="#">Services</a></li>
          <li><a href="#">Contact</a></li>
          <li><a href="tel:{{TELEPHONE}}" class="nav-cta-mobile">Appeler</a></li>""",
        "extra_desktop": "",
        "layout": "grid",
    },
    "artisan/artisan-hero-2-expertise.html": {
        "accent": "#4a7c59",
        "font_line": '<link href="https://fonts.googleapis.com/css2?family=Sora:wght@300;400;600;700;800&family=Lora:ital,wght@0,400;0,600;1,400&display=swap" rel="stylesheet">',
        "desktop_links": """          <li><a href="#">Services</a></li>
          <li><a href="#">À propos</a></li>
          <li><a href="#">Contact</a></li>""",
        "mobile_links": """          <li><a href="#">Accueil</a></li>
          <li><a href="#">Services</a></li>
          <li><a href="#">Contact</a></li>
          <li><a href="tel:{{TELEPHONE}}" class="nav-cta-mobile">Appeler</a></li>""",
        "extra_desktop": """
        <a href="tel:{{TELEPHONE}}" class="nav-cta">📞 {{TELEPHONE}}</a>""",
        "layout": "overlay",
    },
    "sport/sport-hero-2-coach.html": {
        "accent": "#e63946",
        "font_line": '<link href="https://fonts.googleapis.com/css2?family=Sora:wght@300;400;600;700;800&family=Lora:ital,wght@0,400;0,600;1,400&display=swap" rel="stylesheet">',
        "desktop_links": """          <li><a href="#">Services</a></li>
          <li><a href="#">À propos</a></li>
          <li><a href="#">Contact</a></li>""",
        "mobile_links": """          <li><a href="#">Accueil</a></li>
          <li><a href="#">Services</a></li>
          <li><a href="#">Contact</a></li>
          <li><a href="tel:{{TELEPHONE}}" class="nav-cta-mobile">Appeler</a></li>""",
        "extra_desktop": """
        <a href="tel:{{TELEPHONE}}" class="nav-cta">📞 {{TELEPHONE}}</a>""",
        "layout": "overlay",
    },
    "auto/auto-hero-2-moderne.html": {
        "accent": "#1a73e8",
        "font_line": '<link href="https://fonts.googleapis.com/css2?family=Sora:wght@300;400;600;700;800&family=Lora:ital,wght@0,400;0,600;1,400&display=swap" rel="stylesheet">',
        "desktop_links": """          <li><a href="#">Services</a></li>
          <li><a href="#">À propos</a></li>
          <li><a href="#">Contact</a></li>""",
        "mobile_links": """          <li><a href="#">Accueil</a></li>
          <li><a href="#">Services</a></li>
          <li><a href="#">Contact</a></li>
          <li><a href="tel:{{TELEPHONE}}" class="nav-cta-mobile">Appeler</a></li>""",
        "extra_desktop": """
        <a href="tel:{{TELEPHONE}}" class="nav-cta">📞 {{TELEPHONE}}</a>""",
        "layout": "overlay",
    },
}


def make_nav_css(accent):
    return f"""/* ── NAV ── */
nav{{
  display:flex;align-items:center;justify-content:space-between;
  padding:2rem 4rem;
  border-bottom:1px solid rgba(255,255,255,.06);
  background:rgba(0,0,0,.25);
  backdrop-filter:blur(14px);
  -webkit-backdrop-filter:blur(14px);
  position:relative;z-index:1;
  flex-shrink:0;
}}

.nav-logo-img{{height:34px;width:auto;filter:brightness(0) invert(1);display:none}}
.nav-logo-text{{
  font-family:'EB Garamond',serif;
  font-size:1.25rem;font-weight:500;color:#fff;
  text-decoration:none;letter-spacing:.03em;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
}}
.nav-logo-text span{{color:{accent}}}

/* Desktop nav */
.nav-desktop{{
  display:flex;align-items:center;justify-content:space-between;
  width:100%;
}}
.nav-desktop .nav-links{{display:flex;gap:2rem;list-style:none}}
.nav-desktop .nav-links a {{
  font-size:.7rem;font-weight:500;letter-spacing:.14em;text-transform:uppercase;
  color:rgba(255,255,255,.5);text-decoration:none;transition:color .2s;
; color: rgba(255, 255, 255, 0.85) !important; font-weight: 600; text-shadow: 0 1px 4px rgba(0,0,0,0.5);}}
.nav-desktop .nav-links a:hover{{color:{accent}}}

/* Mobile nav */
.nav-mobile{{display:none}}

"""


def make_html_nav(desktop_links, mobile_links, extra_desktop):
    return f"""    <nav>
      <!-- Desktop nav -->
      <div class="nav-desktop">
        <a href="#" class="nav-logo-text nav-name">
          {{{{NOM_ENTREPRISE}}}}<span>.</span>
        </a>
        <ul class="nav-links">
{desktop_links}
        </ul>{extra_desktop}
      </div>

      <!-- Mobile nav -->
      <div class="nav-mobile">
        <input type="checkbox" id="nav-toggle">
        <div class="nav-links-mobile-wrap"></div>
        <ul class="nav-links-mobile">
{mobile_links}
        </ul>
        <a href="tel:{{{{TELEPHONE}}}}" class="nav-bar-tel">📞 {{{{TELEPHONE}}}}</a>
        <a href="#" class="nav-logo-text nav-name">
          {{{{NOM_ENTREPRISE}}}}<span>.</span>
        </a>
        <label for="nav-toggle" class="burger" aria-label="Menu"><span></span></label>
      </div>
    </nav>"""


def apply_changes(filepath, config):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    accent = config["accent"]
    changes = []

    # === CHANGE 1: Add EB Garamond to Google Fonts ===
    old_font = config["font_line"]
    new_font = old_font.replace("family=", "family=EB+Garamond:wght@400;500;700&family=", 1)
    if new_font != old_font:
        content = content.replace(old_font, new_font)
        changes.append("1:fonts")

    # === CHANGE 2: Replace nav CSS section ===
    # From /* ── NAV ── */ to the next section comment (/* ── CONTENU ... ── */)
    nav_css_match = re.search(
        r'(/\* ── NAV ── \*/.*?)(?=/\* ── [A-Z])',
        content, re.DOTALL
    )
    if nav_css_match:
        new_nav_css = make_nav_css(accent)
        content = content[:nav_css_match.start()] + new_nav_css + content[nav_css_match.end():]
        changes.append("2:nav_css")

    # === CHANGE 3: Remove standalone .nav-bar-tel CSS ===
    # Remove .nav-bar-tel{...} .nav-bar-tel:hover{...} block
    content = re.sub(
        r'\.nav-bar-tel\{[^}]*\}\s*\.nav-bar-tel:hover\{[^}]*\}\s*',
        '', content
    )
    # Also remove single-line .nav-bar-tel rules
    content = re.sub(
        r'\.nav-bar-tel\{\s*font-size:[^}]*\}\s*',
        '', content
    )

    # === CHANGE 4: Add mobile nav rules INSIDE first @media(max-width:768px) ===
    # Find the first 768px block and add nav rules before the closing }
    first_768 = re.search(r'@media\(max-width:768px\)\{', content)
    if first_768:
        # Find the matching closing brace
        brace_count = 0
        start_pos = first_768.end()
        end_pos = start_pos
        for i, ch in enumerate(content[start_pos:], start_pos):
            if ch == '{':
                brace_count += 1
            elif ch == '}':
                if brace_count == 0:
                    end_pos = i
                    break
                brace_count -= 1

        # Get the block content
        block = content[start_pos:end_pos]

        # Remove any old nav-related lines from this block
        block = re.sub(r'\s*nav\{padding:[^}]*\}', '', block)
        block = re.sub(r'\s*\.nav-links\{display:none\}', '', block)
        block = re.sub(r'\s*\.burger\{display:block\}', '', block)
        block = re.sub(r'\s*\.nav-bar-tel\{font-size:[^}]*\}', '', block)
        block = re.sub(r'\s*\.nav-logo-text\{[^}]*\}', '', block)
        block = re.sub(r'\s*\.burger\{order:[^}]*\}', '', block)

        # Add mobile nav rules before the closing }
        nav_mobile_rules = """
  .nav-desktop{display:none}
  .nav-mobile{
    display:flex;align-items:center;justify-content:space-between;
    width:100%;padding:1rem 1.25rem;
  }
  .nav-mobile .nav-bar-tel{font-size:.65rem;order:1}
  .nav-mobile .nav-logo-text{order:2;flex:1;text-align:left;padding-left:.75rem;font-size:1rem}
  .nav-mobile .burger{order:3}"""

        content = content[:start_pos] + block + nav_mobile_rules + "\n" + content[end_pos:]
        changes.append("4:768px_nav")

    # === CHANGE 5: Add nav-mobile padding in @media(max-width:480px) ===
    first_480 = re.search(r'@media\(max-width:480px\)\{', content)
    if first_480:
        brace_count = 0
        start_pos = first_480.end()
        end_pos = start_pos
        for i, ch in enumerate(content[start_pos:], start_pos):
            if ch == '{':
                brace_count += 1
            elif ch == '}':
                if brace_count == 0:
                    end_pos = i
                    break
                brace_count -= 1

        block = content[start_pos:end_pos]

        # Remove old nav lines from 480px block
        block = re.sub(r'\s*nav\{padding:[^}]*\!important\}', '', block)
        block = re.sub(r'\s*\.nav-bar-tel\{font-size:[^}]*\}', '', block)
        block = re.sub(r'\s*\.nav-logo-text\{font-size:[^}]*\}', '', block)

        nav_480_rules = """
  .nav-mobile{padding:.75rem 1rem!important}
  .nav-mobile .nav-bar-tel{font-size:.58rem}
  .nav-mobile .nav-logo-text{font-size:.88rem}"""

        content = content[:start_pos] + block + nav_480_rules + "\n" + content[end_pos:]
        changes.append("5:480px_nav")

    # === CHANGE 6: Replace HTML <nav> element ===
    new_nav_html = make_html_nav(
        config["desktop_links"],
        config["mobile_links"],
        config["extra_desktop"]
    )
    if re.search(r'<nav>.*?</nav>', content, re.DOTALL):
        content = re.sub(r'<nav>.*?</nav>', new_nav_html, content, flags=re.DOTALL)
        changes.append("6:html_nav")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return changes


def main():
    for rel_path, config in FILES.items():
        filepath = os.path.join(BASE, rel_path)
        print(f"\n{'='*60}")
        print(f"Processing: {rel_path}")
        if not os.path.exists(filepath):
            print(f"  [ERROR] File not found!")
            continue
        changes = apply_changes(filepath, config)
        print(f"  Applied: {', '.join(changes)}")
    print(f"\n{'='*60}")
    print("All files processed!")


if __name__ == "__main__":
    main()
