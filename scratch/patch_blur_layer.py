# -*- coding: utf-8 -*-
"""
patch_blur_layer.py
====================
Patches all HTML templates to:
1. Replace the old .suite-blur-overlay CSS with the new multi-layer version
2. Add <div class="suite-blur-layer"></div> inside .suite-blur-overlay
"""
import os
import re
import glob

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "synthetiseur", "templates_sites")

# Old CSS to remove and new CSS to add
OLD_CSS_RE = re.compile(
    r'/\* Overlay de flou progressif \*/\n\.suite-blur-overlay \{[^}]+\}\n',
    re.DOTALL
)

# The new CSS block for the overlay
NEW_CSS_BLOCK = """\
/* Overlay de flou progressif — multi-couches */
.suite-blur-overlay {
  position: absolute;
  inset: 0;
  z-index: 10;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding-bottom: 6rem;
  pointer-events: none;
}
/* Couche 1 : voile blanc progressif */
.suite-blur-overlay::before {
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
}
/* Couche 2 : flou progressif via mask */
.suite-blur-layer {
  position: absolute;
  inset: 0;
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  -webkit-mask-image: linear-gradient(to bottom, transparent 0%, transparent 15%, black 45%, black 100%);
  mask-image: linear-gradient(to bottom, transparent 0%, transparent 15%, black 45%, black 100%);
  pointer-events: none;
}
/* La carte CTA au dessus des couches */
.suite-blur-overlay > .suite-blur-card {
  pointer-events: auto;
  position: relative;
  z-index: 5;
}
"""

def patch_template(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    changed = False

    # 1. Replace old .suite-blur-overlay CSS block
    # Find the exact pattern in the template CSS (inside <style> tags)
    old_overlay_css = re.compile(
        r'/\* Overlay de flou progressif \*/\s*\n\.suite-blur-overlay \{[^}]+\}',
        re.DOTALL
    )
    if old_overlay_css.search(content):
        content = old_overlay_css.sub(NEW_CSS_BLOCK.rstrip('\n'), content, count=1)
        changed = True

    # 2. Also remove the old backdrop-filter references inside the old .suite-blur-overlay
    # (these appear in media queries too - just remove the old duplicate backdrop-filter lines)
    old_backdrop_in_overlay = re.compile(
        r'(\s*backdrop-filter: blur\(20px\);\s*\n\s*-webkit-backdrop-filter: blur\(20px\);\s*\n)',
    )
    # Only remove it if it's within the OLD overlay block; we're safe since we already replaced the main block
    content = old_backdrop_in_overlay.sub('\n', content)

    # 3. Add <div class="suite-blur-layer"></div> after the opening <div class="suite-blur-overlay">
    # ONLY if it doesn't already have it
    if '<div class="suite-blur-layer">' not in content:
        content = content.replace(
            '<div class="suite-blur-overlay">',
            '<div class="suite-blur-overlay">\n    <div class="suite-blur-layer"></div>',
            1  # only first occurrence
        )
        changed = True

    if changed:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False


def main():
    html_files = glob.glob(os.path.join(TEMPLATES_DIR, '**', '*.html'), recursive=True)
    print(f"Found {len(html_files)} HTML templates")
    ok, skip = 0, 0
    for fp in sorted(html_files):
        rel = os.path.relpath(fp, TEMPLATES_DIR)
        if patch_template(fp):
            print(f"  [PATCHED] {rel}")
            ok += 1
        else:
            print(f"  [SKIP]    {rel}")
            skip += 1
    print(f"\nDone: {ok} patched, {skip} skipped")


if __name__ == '__main__':
    main()
