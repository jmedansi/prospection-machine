# -*- coding: utf-8 -*-
"""
remove_logo_display.py
=======================
Supprime tous les éléments liés au logo dans la nav des templates :
- <img class="nav-logo-img" ...> (image logo)
- Les blocs {% if LOGO_URL %} / {% else %} / {% endif %}
- .nav-logo-img CSS (hide it)
→ Ne garde que <a class="nav-logo-text">NOM</a>
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

    # ─── 1. Simplifier le bloc Jinja2 : garder uniquement le contenu du {% else %} ───
    # Pattern: {% if LOGO_URL %} ... img ... {% else %} ... <a ...> ... {% endif %}
    jinja_block_re = re.compile(
        r'\{%\s*if\s+LOGO_URL\s*%\}.*?\{%\s*else\s*%\}(.*?)\{%\s*endif\s*%\}',
        re.DOTALL
    )
    content = jinja_block_re.sub(lambda m: m.group(1).strip(), content)

    # ─── 2. Supprimer les <img class="nav-logo-img"> résiduels ─────────────────────
    content = re.sub(
        r'\s*<img[^>]+class="[^"]*nav-logo-img[^"]*"[^>]*>\s*\n?',
        '\n',
        content
    )

    # ─── 3. Masquer .nav-logo-img via CSS (display:none sûr) ──────────────────────
    # Si la règle CSS existe encore, la forcer à display:none
    content = re.sub(
        r'(\.nav-logo-img\{[^}]*?)(display:\s*\w+)',
        r'\1display:none',
        content
    )
    # Si la règle n'avait pas display: ajouter none
    content = re.sub(
        r'(\.nav-logo-img\{)([^}]*?)(\})',
        lambda m: m.group(1) + m.group(2) + 'display:none;' + m.group(3)
        if 'display' not in m.group(2) else m.group(0),
        content
    )

    # ─── 4. S'assurer que .nav-logo-text est display:block ─────────────────────────
    # (au cas où un previous inject l'aurait mis en display:none)
    # On ne touche pas le CSS du template ici, le CSS injecté par inject_profil_a.py
    # a déjà `display: block !important` sur .nav-logo-text

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
            print(f"  [skip]  {rel}")
            skip += 1
    print(f"\n✓ {ok} fixed, {skip} unchanged")

if __name__ == '__main__':
    main()
