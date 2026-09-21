#!/usr/bin/env python3
"""
Patch all 26 sector templates:
1. Inject hamburger CSS + mobile CSS
2. Inject hamburger HTML into nav
3. Fix split-layout mobile (hero-right → background)
"""
import os, re, glob

BASE = r"D:\prospection-machine\synthetiseur\templates_sites"

# ── HAMBURGER CSS ──
HAMBURGER_CSS = """
/* ── HAMBURGER MOBILE ── */
.burger{display:none;cursor:pointer;width:28px;height:22px;position:relative;z-index:20}
.burger span,.burger::before,.burger::after{
  display:block;width:100%;height:2px;background:#fff;
  border-radius:2px;transition:all .3s;position:absolute;left:0}
.burger::before{content:'';top:0}
.burger span{top:50%;transform:translateY(-50%)}
.burger::after{content:'';bottom:0}
#nav-toggle{display:none}
#nav-toggle:checked~.nav-links-mobile{transform:translateX(0)}
#nav-toggle:checked~label.burger span{opacity:0}
#nav-toggle:checked~label.burger::before{top:50%;transform:translateY(-50%) rotate(45deg)}
#nav-toggle:checked~label.burger::after{bottom:auto;top:50%;transform:translateY(-50%) rotate(-45deg)}
.nav-links-mobile{
  position:fixed;top:0;right:0;width:75vw;max-width:320px;height:100vh;
  background:rgba(10,10,10,.97);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
  display:flex;flex-direction:column;justify-content:center;align-items:center;gap:2rem;
  transform:translateX(100%);transition:transform .35s cubic-bezier(.16,1,.3,1);z-index:15;
}
.nav-links-mobile a{
  font-size:.85rem;font-weight:600;letter-spacing:.12em;text-transform:uppercase;
  color:rgba(255,255,255,.8);text-decoration:none;transition:color .2s}
.nav-links-mobile a:hover{color:#fff}
.nav-links-mobile .nav-cta-mobile{
  margin-top:1rem;padding:.75rem 2rem;
  border:1px solid rgba(255,255,255,.3);border-radius:3px;font-size:.8rem}
"""

HAMBURGER_HTML = """<input type="checkbox" id="nav-toggle">
<label for="nav-toggle" class="burger" aria-label="Menu"><span></span></label>
<ul class="nav-links-mobile">
  <li><a href="#">Accueil</a></li>
  <li><a href="#">Services</a></li>
  <li><a href="#">Contact</a></li>
  <li><a href="tel:{{TELEPHONE}}" class="nav-cta-mobile">Appeler</a></li>
</ul>"""

# Split-layout templates that need hero-right → background on mobile
SPLIT_LAYOUT = [
    "hotellerie-hero-2-urbain",
    "beaute-hero-2-moderne",
    "immobilier-hero-2-moderne",
    "default-hero-2-chaleureux",
]


def get_all_templates():
    templates = []
    for sector_dir in sorted(glob.glob(os.path.join(BASE, "*"))):
        if not os.path.isdir(sector_dir):
            continue
        sector = os.path.basename(sector_dir)
        for f in sorted(glob.glob(os.path.join(sector_dir, "*.html"))):
            if f.endswith("index.html"):
                continue
            name = os.path.splitext(os.path.basename(f))[0]
            templates.append((sector, name, f))
    return templates


def inject_hamburger_css(content):
    """Inject hamburger CSS before first @media or before </style>"""
    if ".burger{" in content:
        return content  # already patched

    # Find first @media or </style>
    m = re.search(r'@media\s*\(', content)
    if m:
        pos = m.start()
    else:
        m = re.search(r'</style>', content)
        if m:
            pos = m.start()
        else:
            return content

    return content[:pos] + HAMBURGER_CSS + "\n" + content[pos:]


def inject_hamburger_html(content):
    """Inject hamburger HTML after first <nav> opening tag"""
    if '<input type="checkbox" id="nav-toggle">' in content:
        return content  # already patched

    # Match <nav> with optional whitespace/newline after
    m = re.search(r'(<nav[^>]*>)', content, re.IGNORECASE)
    if not m:
        return content

    end = m.end()
    return content[:end] + "\n" + HAMBURGER_HTML + "\n" + content[end:]


def fix_mobile_css(content, is_split):
    """Replace @media(max-width:768px) block to add .burger display and nav-links hide"""

    # Pattern 1: Template-specific 768px block (has hero-specific rules)
    # We need to add .burger{display:block} and keep .nav-links{display:none}

    # Add .burger{display:block} to the first 768px block that has .nav-links{display:none}
    if ".nav-links{display:none}" in content and ".burger{display:block}" not in content:
        content = content.replace(
            ".nav-links{display:none}",
            ".nav-links{display:none}\n  .burger{display:block}",
            1
        )

    # For split-layout templates: replace hero-right display:none with background treatment
    if is_split:
        # Replace the hero-right display:none in the 768px block
        old_split = re.search(
            r'(@media\s*\(\s*max-width\s*:\s*768px\s*\)\s*\{[^}]*\.hero-right\s*\{\s*display\s*:\s*none\s*\})',
            content
        )
        if old_split:
            # Find the full 768px block and replace the hero-right part
            content = re.sub(
                r'(\.hero-right\{[^}]*display\s*:\s*none[^}]*\})',
                """.hero-right{
    position:absolute;top:0;left:0;right:0;bottom:0;
    display:block!important;z-index:0}
  .hero-right img,.hero-img{
    width:100%!important;height:100%!important;object-fit:cover;
    filter:brightness(0.4)}
  .hero-left{position:relative;z-index:1;
    background:linear-gradient(180deg,rgba(0,0,0,.5) 0%,rgba(0,0,0,.2) 100%)}""",
                content,
                count=1
            )

    return content


def fix_split_hero_mobile(content, template_name):
    """For split-layout templates, make hero-right a background on mobile"""
    if template_name not in SPLIT_LAYOUT:
        return content

    # Already patched?
    if "position:absolute;top:0;left:0;right:0;bottom:0" in content:
        return content

    return content


def fix_font_spacing(content):
    """Apply font/spacing improvements across all templates"""

    # Fix the shared 768px mobile block: increase hero-desc font
    # The shared block has: .hero-desc,.hero-description,.hero-text{font-size:.88rem!important}
    # We leave this as-is since it's a shared override; individual template styles handle the base

    # Fix small phone 480px: increase nav CTA font
    content = re.sub(
        r'(\.nav-cta[^,{]*,\.nav-rdv[^,{]*,\.nav-tel[^,{]*)\{font-size:\.62rem',
        r'\1{font-size:.7rem',
        content
    )

    return content


def process_template(sector, name, filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content
    is_split = any(s in name for s in SPLIT_LAYOUT)

    content = inject_hamburger_css(content)
    content = inject_hamburger_html(content)
    content = fix_mobile_css(content, is_split)
    content = fix_font_spacing(content)

    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False


def main():
    templates = get_all_templates()
    print(f"Found {len(templates)} templates\n")

    patched = 0
    for sector, name, filepath in templates:
        result = process_template(sector, name, filepath)
        status = "PATCHED" if result else "skip"
        print(f"  [{status}] {sector}/{name}")
        if result:
            patched += 1

    print(f"\n{patched}/{len(templates)} templates patched")


if __name__ == "__main__":
    main()
