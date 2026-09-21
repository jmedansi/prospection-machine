#!/usr/bin/env python3
"""Apply dual nav changes to all 12 hero-2 templates."""

import re
import os

BASE = r"D:\prospection-machine\synthetiseur\templates_sites"

FILES = {
    "restaurant/restaurant-hero-2-chaleureux.html": {
        "accent": "#d4822a",
        "font_line": '<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;0,900;1,400;1,700&family=Lato:wght@300;400;700&display=swap" rel="stylesheet">',
        "desktop_links": """<li><a href="#">La carte</a></li>
          <li><a href="#">Notre histoire</a></li>
          <li><a href="#">Contact</a></li>""",
        "mobile_links": """<li><a href="#">Accueil</a></li>
          <li><a href="#">Services</a></li>
          <li><a href="#">Contact</a></li>
          <li><a href="tel:{{TELEPHONE}}" class="nav-cta-mobile">Appeler</a></li>""",
        "extra_desktop": "",
        "nav_logo_font": "font-family:'Playfair Display',serif;",
        "layout": "overlay",
    },
    "sante/sante-hero-2-lumineux.html": {
        "accent": "#00b4d8",
        "font_line": '<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=Plus+Jakarta+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">',
        "desktop_links": """<li><a href="#">Spécialités</a></li>
          <li><a href="#">L'équipe</a></li>
          <li><a href="#">Tarifs</a></li>
          <li><a href="#">Contact</a></li>""",
        "mobile_links": """<li><a href="#">Accueil</a></li>
          <li><a href="#">Services</a></li>
          <li><a href="#">Contact</a></li>
          <li><a href="tel:{{TELEPHONE}}" class="nav-cta-mobile">Appeler</a></li>""",
        "extra_desktop": """
        <div class="nav-right">
          <span class="nav-tel-text">{{TELEPHONE}}</span>
          <a href="#" class="nav-btn">Prendre RDV</a>
        </div>""",
        "nav_logo_font": "font-family:'DM Serif Display',serif;",
        "layout": "overlay",
    },
    "immobilier/immobilier-hero-2-moderne.html": {
        "accent": "#e07a5f",
        "font_line": '<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=Lora:ital,wght@0,400;1,400&display=swap" rel="stylesheet">',
        "desktop_links": """<li><a href="#">Acheter</a></li>
          <li><a href="#">Vendre</a></li>
          <li><a href="#">Estimer</a></li>
          <li><a href="#">Contact</a></li>""",
        "mobile_links": """<li><a href="#">Accueil</a></li>
          <li><a href="#">Services</a></li>
          <li><a href="#">Contact</a></li>
          <li><a href="tel:{{TELEPHONE}}" class="nav-cta-mobile">Appeler</a></li>""",
        "extra_desktop": "",
        "nav_logo_font": "font-size:1.1rem;font-weight:800;",
        "layout": "grid",
    },
    "bijouterie/bijouterie-hero-2-tendance.html": {
        "accent": "#c77dff",
        "font_line": '<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;0,900;1,400&family=Outfit:wght@300;400;500;600&display=swap" rel="stylesheet">',
        "desktop_links": """<li><a href="#">Collections</a></li>
          <li><a href="#">Sur mesure</a></li>
          <li><a href="#">À propos</a></li>
          <li><a href="#">Contact</a></li>""",
        "mobile_links": """<li><a href="#">Accueil</a></li>
          <li><a href="#">Services</a></li>
          <li><a href="#">Contact</a></li>
          <li><a href="tel:{{TELEPHONE}}" class="nav-cta-mobile">Appeler</a></li>""",
        "extra_desktop": """
        <a href="tel:{{TELEPHONE}}" class="nav-cta">📞 {{TELEPHONE}}</a>""",
        "nav_logo_font": "font-family:'Playfair Display',serif;",
        "layout": "overlay",
    },
    "beaute/beaute-hero-2-moderne.html": {
        "accent": "#f4a261",
        "font_line": '<link href="https://fonts.googleapis.com/css2?family=Anton&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">',
        "desktop_links": """<li><a href="#">Services</a></li>
          <li><a href="#">Équipe</a></li>
          <li><a href="#">Tarifs</a></li>""",
        "mobile_links": """<li><a href="#">Accueil</a></li>
          <li><a href="#">Services</a></li>
          <li><a href="#">Contact</a></li>
          <li><a href="tel:{{TELEPHONE}}" class="nav-cta-mobile">Appeler</a></li>""",
        "extra_desktop": """
        <a href="#" class="nav-btn">Book now</a>""",
        "nav_logo_font": "font-family:'Anton',sans-serif;",
        "layout": "inverted",
    },
    "commerce/commerce-hero-2-artisan.html": {
        "accent": "#2a9d8f",
        "font_line": '<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;1,400&family=Outfit:wght@300;400;500;600&display=swap" rel="stylesheet">',
        "desktop_links": """<li><a href="#">Produits</a></li>
          <li><a href="#">À propos</a></li>
          <li><a href="#">Horaires</a></li>
          <li><a href="#">Contact</a></li>""",
        "mobile_links": """<li><a href="#">Accueil</a></li>
          <li><a href="#">Services</a></li>
          <li><a href="#">Contact</a></li>
          <li><a href="tel:{{TELEPHONE}}" class="nav-cta-mobile">Appeler</a></li>""",
        "extra_desktop": """
        <a href="tel:{{TELEPHONE}}" class="nav-cta">📞 {{TELEPHONE}}</a>""",
        "nav_logo_font": "font-family:'Playfair Display',serif;",
        "layout": "overlay",
    },
    "juridique/juridique-hero-2-moderne.html": {
        "accent": "#2d6a4f",
        "font_line": '<link href="https://fonts.googleapis.com/css2?family=Libre+Baskerville:ital,wght@0,400;0,700;1,400&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">',
        "desktop_links": """<li><a href="#">Expertises</a></li>
          <li><a href="#">Le cabinet</a></li>
          <li><a href="#">Tarifs</a></li>
          <li><a href="#">Contact</a></li>""",
        "mobile_links": """<li><a href="#">Accueil</a></li>
          <li><a href="#">Services</a></li>
          <li><a href="#">Contact</a></li>
          <li><a href="tel:{{TELEPHONE}}" class="nav-cta-mobile">Appeler</a></li>""",
        "extra_desktop": """
        <a href="#" class="nav-cta">Prendre RDV</a>""",
        "nav_logo_font": "font-family:'Libre Baskerville',serif;",
        "layout": "overlay",
    },
    "hotellerie/hotellerie-hero-2-urbain.html": {
        "accent": "#e9c46a",
        "font_line": '<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=Inter:wght@300;400;500&display=swap" rel="stylesheet">',
        "desktop_links": """<li><a href="#">Chambres</a></li>
          <li><a href="#">Services</a></li>
          <li><a href="#">Contact</a></li>""",
        "mobile_links": """<li><a href="#">Accueil</a></li>
          <li><a href="#">Services</a></li>
          <li><a href="#">Contact</a></li>
          <li><a href="tel:{{TELEPHONE}}" class="nav-cta-mobile">Appeler</a></li>""",
        "extra_desktop": "",
        "nav_logo_font": "font-family:'Syne',sans-serif;font-size:1.1rem;font-weight:800;text-transform:uppercase;",
        "layout": "grid",
    },
    "artisan/artisan-hero-2-expertise.html": {
        "accent": "#4a7c59",
        "font_line": '<link href="https://fonts.googleapis.com/css2?family=Sora:wght@300;400;600;700;800&family=Lora:ital,wght@0,400;0,600;1,400&display=swap" rel="stylesheet">',
        "desktop_links": """<li><a href="#">Services</a></li>
          <li><a href="#">À propos</a></li>
          <li><a href="#">Contact</a></li>""",
        "mobile_links": """<li><a href="#">Accueil</a></li>
          <li><a href="#">Services</a></li>
          <li><a href="#">Contact</a></li>
          <li><a href="tel:{{TELEPHONE}}" class="nav-cta-mobile">Appeler</a></li>""",
        "extra_desktop": """
        <a href="tel:{{TELEPHONE}}" class="nav-cta">📞 {{TELEPHONE}}</a>""",
        "nav_logo_font": "font-family:'Sora',sans-serif;",
        "layout": "overlay",
    },
    "sport/sport-hero-2-coach.html": {
        "accent": "#e63946",
        "font_line": '<link href="https://fonts.googleapis.com/css2?family=Sora:wght@300;400;600;700;800&family=Lora:ital,wght@0,400;0,600;1,400&display=swap" rel="stylesheet">',
        "desktop_links": """<li><a href="#">Services</a></li>
          <li><a href="#">À propos</a></li>
          <li><a href="#">Contact</a></li>""",
        "mobile_links": """<li><a href="#">Accueil</a></li>
          <li><a href="#">Services</a></li>
          <li><a href="#">Contact</a></li>
          <li><a href="tel:{{TELEPHONE}}" class="nav-cta-mobile">Appeler</a></li>""",
        "extra_desktop": """
        <a href="tel:{{TELEPHONE}}" class="nav-cta">📞 {{TELEPHONE}}</a>""",
        "nav_logo_font": "font-family:'Sora',sans-serif;",
        "layout": "overlay",
    },
    "auto/auto-hero-2-moderne.html": {
        "accent": "#1a73e8",
        "font_line": '<link href="https://fonts.googleapis.com/css2?family=Sora:wght@300;400;600;700;800&family=Lora:ital,wght@0,400;0,600;1,400&display=swap" rel="stylesheet">',
        "desktop_links": """<li><a href="#">Services</a></li>
          <li><a href="#">À propos</a></li>
          <li><a href="#">Contact</a></li>""",
        "mobile_links": """<li><a href="#">Accueil</a></li>
          <li><a href="#">Services</a></li>
          <li><a href="#">Contact</a></li>
          <li><a href="tel:{{TELEPHONE}}" class="nav-cta-mobile">Appeler</a></li>""",
        "extra_desktop": """
        <a href="tel:{{TELEPHONE}}" class="nav-cta">📞 {{TELEPHONE}}</a>""",
        "nav_logo_font": "font-family:'Sora',sans-serif;",
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


def make_mobile_media():
    return """  .nav-desktop{display:none}
  .nav-mobile{
    display:flex;align-items:center;justify-content:space-between;
    width:100%;padding:1rem 1.25rem;
  }
  .nav-mobile .nav-bar-tel{font-size:.65rem;order:1}
  .nav-mobile .nav-logo-text{order:2;flex:1;text-align:left;padding-left:.75rem;font-size:1rem}
  .nav-mobile .burger{order:3}
"""


def make_480_media():
    return """  .nav-mobile{padding:.75rem 1rem!important}
  .nav-mobile .nav-bar-tel{font-size:.58rem}
  .nav-mobile .nav-logo-text{font-size:.88rem}
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

    # === CHANGE 1: Add EB Garamond to Google Fonts ===
    old_font = config["font_line"]
    # Add EB+Garamond:wght@400;500;700& at the beginning of the font list
    new_font = old_font.replace(
        "family=",
        "family=EB+Garamond:wght@400;500;700&family=",
        1
    )
    if new_font != old_font:
        content = content.replace(old_font, new_font)
        print(f"  [OK] CHANGE 1: Added EB Garamond to fonts")
    else:
        print(f"  [WARN] CHANGE 1: Could not find font line to modify")

    # === CHANGE 2: Replace nav CSS section ===
    # Find from /* ── NAV ── */ to /* ── CONTENU ── */ or /* ── CONTENU ... ── */
    nav_css_pattern = r'/\* ── NAV ── \*/.*?(?=/\* ── (?:CONTENU|HERO))'
    new_nav_css = make_nav_css(accent)
    if re.search(nav_css_pattern, content, re.DOTALL):
        content = re.sub(nav_css_pattern, new_nav_css.rstrip(), content, flags=re.DOTALL)
        print(f"  [OK] CHANGE 2: Replaced nav CSS section")
    else:
        print(f"  [WARN] CHANGE 2: Could not find nav CSS section")

    # === CHANGE 3: Update first @media(max-width:768px) block ===
    # Replace old nav rules in the first 768px media query
    old_media_768_nav = re.search(
        r'@media\(max-width:768px\)\{(.*?)(?=/\* -- RESPONSIVE|$)',
        content,
        re.DOTALL
    )
    if old_media_768_nav:
        block = old_media_768_nav.group(1)
        # Remove old nav-related lines
        new_block = re.sub(
            r'\s*nav\{padding:[^}]*\}',
            '',
            block
        )
        new_block = re.sub(
            r'\s*\.nav-links\{display:none\}',
            '',
            new_block
        )
        new_block = re.sub(
            r'\s*\.burger\{display:block\}',
            '',
            new_block
        )
        new_block = re.sub(
            r'\s*\.nav-bar-tel\{font-size:[^}]*\}',
            '',
            new_block
        )
        new_block = re.sub(
            r'\s*\.nav-logo-text\{[^}]*\}',
            '',
            new_block
        )
        new_block = re.sub(
            r'\s*\.burger\{order:[^}]*\}',
            '',
            new_block
        )
        # Add new mobile nav rules
        new_block = new_block.rstrip() + "\n" + make_mobile_media()
        content = content[:old_media_768_nav.start()] + "@media(max-width:768px){" + new_block + content[old_media_768_nav.end():]
        print(f"  [OK] CHANGE 3: Updated 768px media query nav rules")
    else:
        print(f"  [WARN] CHANGE 3: Could not find 768px media query")

    # === CHANGE 4: Update @media(max-width:480px) block ===
    # Replace nav-related lines in 480px media query
    old_480_block = re.search(
        r'@media\(max-width:480px\)\{(.*?)\n\}',
        content,
        re.DOTALL
    )
    if old_480_block:
        block = old_480_block.group(1)
        new_block = re.sub(
            r'\s*nav\{padding:[^}]*\!important\}',
            '',
            block
        )
        new_block = re.sub(
            r'\s*\.nav-bar-tel\{font-size:[^}]*\}',
            '',
            new_block
        )
        new_block = re.sub(
            r'\s*\.nav-logo-text\{font-size:[^}]*\}',
            '',
            new_block
        )
        new_block = new_block.rstrip() + "\n" + make_480_media()
        content = content[:old_480_block.start()] + "@media(max-width:480px){" + new_block + "\n}" + content[old_480_block.end():]
        print(f"  [OK] CHANGE 4: Updated 480px media query nav rules")
    else:
        print(f"  [WARN] CHANGE 4: Could not find 480px media query")

    # === CHANGE 5: Replace HTML nav structure ===
    # Find the <nav>...</nav> block and replace it
    nav_html_pattern = r'<nav>.*?</nav>'
    new_nav_html = make_html_nav(
        config["desktop_links"],
        config["mobile_links"],
        config["extra_desktop"]
    )
    if re.search(nav_html_pattern, content, re.DOTALL):
        content = re.sub(nav_html_pattern, new_nav_html, content, flags=re.DOTALL)
        print(f"  [OK] CHANGE 5: Replaced HTML nav structure")
    else:
        print(f"  [WARN] CHANGE 5: Could not find HTML nav element")

    # === ALSO: Remove old standalone .nav-bar-tel CSS ===
    content = re.sub(
        r'\.nav-bar-tel\{[^}]*\}\s*\.nav-bar-tel:hover\{[^}]*\}\s*',
        '',
        content
    )
    # Also remove if it's a single rule
    content = re.sub(
        r'\.nav-bar-tel\{\s*font-size:[^}]*color:rgba\(255,255,255,[^}]*\}\s*\.nav-bar-tel:hover\{color:#fff\}\s*',
        '',
        content
    )

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)


def main():
    for rel_path, config in FILES.items():
        filepath = os.path.join(BASE, rel_path)
        print(f"\n{'='*60}")
        print(f"Processing: {rel_path}")
        print(f"  Accent: {config['accent']}")
        if not os.path.exists(filepath):
            print(f"  [ERROR] File not found!")
            continue
        apply_changes(filepath, config)
    print(f"\n{'='*60}")
    print("All files processed!")


if __name__ == "__main__":
    main()
