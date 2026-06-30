# -*- coding: utf-8 -*-
"""
fix_width_and_nav.py
=====================
Corrige dans tous les templates HTML :
1. "; max-width: 800px; width: 60%;}" — supprimer cet override mal placé (syntaxe invalide)
2. Dans les media queries : ".hero-content/inner {... max-width: 800px; width: 60%;}" → width: 100%
3. Nav logo : img + texte superposés → wrapping avec {% if LOGO_URL %}
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import os, re, glob

TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "synthetiseur", "templates_sites"
)

def fix_template(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content
    
    # ─── FIX 1 : Supprimer la ligne "; max-width: 800px; width: 60%;}" ───────────────
    # Cette ligne est ajoutée à la fin d'un bloc CSS comme override invalide
    content = re.sub(
        r'\n;?\s*max-width:\s*800px;\s*width:\s*60%;\s*\}',
        '\n}',
        content
    )
    
    # ─── FIX 2 : Dans les media queries, retirer width: 60% et max-width: 800px ───────
    # Garder le padding mais corriger la contrainte de largeur
    def fix_media_content(m):
        full = m.group(0)
        # Remove the width: 60% and max-width: 800px from the single-line declaration
        full = re.sub(r';\s*max-width:\s*800px', '', full)
        full = re.sub(r';\s*width:\s*60%', '', full)
        # Add max-width: 100% if not present
        if 'max-width:100%' not in full and 'max-width: 100%' not in full:
            full = re.sub(r'(\.(hero-content|hero-inner)\s*\{)', r'\1 max-width:100%;', full)
        return full
    
    content = re.sub(
        r'@media\([^)]+\)\s*\{[^}]*\.(hero-content|hero-inner)\s*\{[^}]+\}[^}]*\}',
        fix_media_content,
        content,
        flags=re.DOTALL
    )
    
    # Simpler approach: directly replace the pattern in media queries
    content = re.sub(
        r'(\.(hero-content|hero-inner)\s*\{[^}]*?);\s*max-width:\s*800px;\s*width:\s*60%;?\s*(\})',
        r'\1;\n    max-width: 100%;\3',
        content
    )
    
    # ─── FIX 3 : Nav logo superposition ─────────────────────────────────────────────
    # Skip templates that already use {% if LOGO_URL %}
    already_guarded = '{% if LOGO_URL %}' in content
    
    if not already_guarded:
        # Look for: <img src="{{LOGO_URL}}" class="nav-logo-img"...> followed by
        #           <a ... class="nav-logo-text"...>...</a>
        # → wrap them with {% if %} / {% else %} / {% endif %}
        
        # Pattern: whitespace img_tag newline whitespace a_tag
        nav_pattern = re.compile(
            r'(\s{4,})(<img[^>]+src="{{LOGO_URL}}"[^>]*>)\s*\n'
            r'(\s{4,})(<a[^>]+class="[^"]*nav-logo-text[^"]*"[^>]*>.*?</a>)',
            re.DOTALL
        )
        
        def wrap_nav(m):
            indent = m.group(1)
            img = m.group(2).strip()
            a = m.group(4).strip()
            return (
                f"{indent}{{% if LOGO_URL %}}\n"
                f"{indent}  {img}\n"
                f"{indent}{{% else %}}\n"
                f"{indent}  {a}\n"
                f"{indent}{{% endif %}}"
            )
        
        content, n = nav_pattern.subn(wrap_nav, content, count=1)
        if n > 0 and 'nav-logo-img' in content:
            pass  # patched
    
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

def main():
    files = glob.glob(os.path.join(TEMPLATES_DIR, '**', '*.html'), recursive=True)
    print(f"Scanning {len(files)} templates...\n")
    ok = skip = 0
    for fp in sorted(files):
        rel = os.path.relpath(fp, TEMPLATES_DIR)
        if fix_template(fp):
            print(f"  [FIXED] {rel}")
            ok += 1
        else:
            skip += 1
    print(f"\n✓ {ok} fixed, {skip} unchanged")

if __name__ == '__main__':
    main()
