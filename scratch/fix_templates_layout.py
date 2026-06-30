# -*- coding: utf-8 -*-
"""
fix_templates_layout.py
========================
Corrige deux bugs dans tous les templates :
1. Nav : si l'img logo n'a pas de {% if LOGO_URL %}, les deux (img+texte) se superposent
2. hero-content width:60% trop restrictif → le contenu est coincé à gauche

Fixes appliqués :
- .hero-content : width → max-width:55% sur desktop, 100% sur mobile
- nav logo : wrapping dans {% if LOGO_URL %} si absent
"""
import os
import re
import glob
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "synthetiseur", "templates_sites"
)

# ─── FIX 1 : .hero-content width ─────────────────────────────────────────────
# Patterns: "; max-width: 800px; width: 60%;}" and similar inline width constraints
HERO_CONTENT_WIDTH_RE = re.compile(
    r'(\.hero-content\s*\{[^}]*?)(?:;\s*max-width:\s*\d+px;\s*width:\s*\d+%;?\s*)?(\})',
    re.DOTALL
)

# ─── FIX 2 : nav logo superposition ──────────────────────────────────────────
# Detect: <img src="{{LOGO_URL}}" class="nav-logo-img" ...> WITHOUT {% if LOGO_URL %} guard
# These are on separate consecutive lines in the nav div
NAV_IMG_UNGUARDED_RE = re.compile(
    r'(<div[^>]*style="display:flex[^>]*>)\s*\n'
    r'(\s*<img\s+src="{{LOGO_URL}}"[^>]*class="[^"]*nav-logo-img[^"]*"[^>]*>)\s*\n'
    r'(\s*<a\s+href="#"\s+class="[^"]*nav-logo-text[^"]*"[^>]*>.*?</a>)',
    re.DOTALL
)

# Pattern 2 alternative - some templates have {% if LOGO_URL %} already (correct)
# Others have the img directly:
NAV_IMG_BARE_RE = re.compile(
    r'(\s*)(<img\s+src="{{LOGO_URL}}"[^>]*class="[^"]*nav-logo-img[^"]*"[^>]*>)\s*\n'
    r'(\s*)(<a\s+href="#"\s+class="[^"]*nav-logo-text[^"]*"[^>]*>.*?</a>)',
    re.DOTALL
)

# Correct form with jinja guards - check if already correct
ALREADY_GUARDED_RE = re.compile(r'\{%\s*if\s+LOGO_URL\s*%\}')


def fix_hero_content_width(content: str) -> tuple[str, bool]:
    """Fix .hero-content width constraint in CSS."""
    changed = False
    
    # Fix: "; max-width: 800px; width: 60%;}" inline style appended by inject script
    # This pattern appears as a second declaration after the closing brace is reused
    # Example: .hero-content {\n  ....\n; max-width: 800px; width: 60%;}
    bad_inline = re.compile(
        r'(\.hero-content\s*\{[^}]*?)\n;?\s*max-width:\s*\d+px;\s*width:\s*\d+%;\s*\}',
        re.DOTALL
    )
    if bad_inline.search(content):
        content = bad_inline.sub(r'\1\n  max-width: 55%;\n}', content)
        changed = True
    
    # Also fix in media query: ".hero-content {padding:...; max-width: 800px; width: 60%;}"
    bad_media_inline = re.compile(
        r'(\.hero-content\s*\{[^}]*?)\s*;\s*max-width:\s*\d+px;\s*width:\s*\d+%;\s*\}',
        re.DOTALL
    )
    if bad_media_inline.search(content):
        content = bad_media_inline.sub(r'\1\n    max-width: 100%;\n  }', content)
        changed = True
    
    # Fix hero-content max-width that's too narrow (like max-width: 760px)  
    # Replace with proper 50% constraint
    narrow_max = re.compile(r'(\.hero-content\s*\{[^}]*?max-width:)\s*760px', re.DOTALL)
    if narrow_max.search(content):
        content = narrow_max.sub(r'\g<1> 55vw', content)
        changed = True
    
    return content, changed


def fix_nav_logo_superposition(content: str) -> tuple[str, bool]:
    """Fix nav logo: wrap img in {% if LOGO_URL %} if not already guarded."""
    changed = False
    
    # Skip if already properly guarded with Jinja2 if block
    if ALREADY_GUARDED_RE.search(content):
        return content, False
    
    # Look for the unguarded pattern: img logo + text logo side by side without if guard
    # Pattern: <img src="{{LOGO_URL}}" class="nav-logo-img" ...> immediately followed by
    #          <a ... class="nav-logo-text ...">...</a>
    bare_img_text = re.compile(
        r'(\s*)(<img[^>]+src="{{LOGO_URL}}"[^>]*class="[^"]*nav-logo-img[^"]*"[^>]*>)\s*\n'
        r'(\s*)(<a[^>]+class="[^"]*nav-logo-text[^"]*"[^>]*>.*?</a>)',
        re.DOTALL
    )
    
    def replace_with_guard(m):
        indent1 = m.group(1)
        img_tag = m.group(2)
        indent2 = m.group(3)
        text_tag = m.group(4)
        return (
            f"\n{indent1}{{% if LOGO_URL %}}\n"
            f"{indent1}  {img_tag}\n"
            f"{indent1}{{% else %}}\n"
            f"{indent2}{text_tag}\n"
            f"{indent1}{{% endif %}}"
        )
    
    new_content, n = bare_img_text.subn(replace_with_guard, content)
    if n > 0:
        content = new_content
        changed = True
    
    return content, changed


def patch_template(filepath: str) -> bool:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    content, fix1 = fix_hero_content_width(content)
    content, fix2 = fix_nav_logo_superposition(content)
    
    if fix1 or fix2:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        fixes = []
        if fix1: fixes.append('width')
        if fix2: fixes.append('nav-logo')
        print(f"  [FIXED:{','.join(fixes)}] {os.path.relpath(filepath, TEMPLATES_DIR)}")
        return True
    else:
        print(f"  [OK]     {os.path.relpath(filepath, TEMPLATES_DIR)}")
        return False


def main():
    html_files = glob.glob(os.path.join(TEMPLATES_DIR, '**', '*.html'), recursive=True)
    print(f"Scanning {len(html_files)} templates...\n")
    fixed = 0
    for fp in sorted(html_files):
        if patch_template(fp):
            fixed += 1
    print(f"\nDone: {fixed}/{len(html_files)} templates patched")


if __name__ == '__main__':
    main()
