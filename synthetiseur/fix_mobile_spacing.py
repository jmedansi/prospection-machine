#!/usr/bin/env python3
"""
Fix mobile spacing v4 — targeted approach per template type
"""
import os, glob

BASE = r"D:\prospection-machine\synthetiseur\templates_sites"

HERO_2_SPLIT = [
    "hotellerie-hero-2-urbain", "immobilier-hero-2-moderne",
    "default-hero-2-chaleureux", "beaute-hero-2-moderne",
]

HERO_2_NON_SPLIT = [
    "restaurant-hero-2-chaleureux", "sante-hero-2-lumineux", "artisan-hero-2-expertise",
    "auto-hero-2-moderne", "bijouterie-hero-2-tendance", "commerce-hero-2-artisan",
    "juridique-hero-2-moderne", "sport-hero-2-coach",
]


def get_filepath(name):
    for sector_dir in glob.glob(os.path.join(BASE, "*")):
        if not os.path.isdir(sector_dir):
            continue
        f = os.path.join(sector_dir, name + ".html")
        if os.path.exists(f):
            return f
    return None


def inject_after_first_media_768(content, injection):
    """Find first @media(max-width:768px){ and inject after opening brace, if not already present"""
    idx = content.find("@media(max-width:768px){")
    if idx == -1:
        return content, False
    brace_pos = content.index("{", idx)
    # Check if already present (check next 200 chars)
    snippet = content[brace_pos+1:brace_pos+200]
    # Use first 25 chars of injection as unique key
    key = injection.strip()[:25]
    if key in snippet:
        return content, False
    content = content[:brace_pos+1] + "\n  " + injection + content[brace_pos+1:]
    return content, True


def fix_hero_2_split(content, name):
    """For split-layout: add height:auto to hero-left in 768px block"""
    # Check if height:auto already in the hero-left context
    if "height:auto;min-height:100vh" in content:
        return content

    # Find the hero-left rule in the 768px block
    # Pattern: .hero-left{...min-height:100vh...}
    idx = content.find("@media(max-width:768px){")
    if idx == -1:
        return content

    # Find the end of this media block
    brace_count = 0
    end = -1
    for i in range(idx, len(content)):
        if content[i] == '{':
            brace_count += 1
        elif content[i] == '}':
            brace_count -= 1
            if brace_count == 0:
                end = i
                break

    if end == -1:
        return content

    block = content[idx:end+1]

    # Find .hero-left{...} within this block
    hl_start = block.find(".hero-left{")
    if hl_start == -1:
        return content

    # Find the closing brace of .hero-left
    hl_brace = block.index("{", hl_start)
    hl_brace_count = 0
    hl_end = -1
    for i in range(hl_brace, len(block)):
        if block[i] == '{':
            hl_brace_count += 1
        elif block[i] == '}':
            hl_brace_count -= 1
            if hl_brace_count == 0:
                hl_end = i
                break

    if hl_end == -1:
        return content

    hl_block = block[hl_start:hl_end+1]

    # Replace min-height:100vh with height:auto;min-height:100vh
    if "min-height:100vh" in hl_block and "height:auto" not in hl_block:
        new_hl = hl_block.replace("min-height:100vh", "height:auto;min-height:100vh", 1)
        new_block = block[:hl_start] + new_hl + block[hl_end+1:]
        content = content[:idx] + new_block + content[end+1:]

    return content


def fix_hero_2_non_split(content):
    """Add height:auto to hero in first 768px block"""
    content, _ = inject_after_first_media_768(content, ".hero{height:auto!important}")
    return content


def main():
    sp, ns = 0, 0

    for name in HERO_2_SPLIT:
        fp = get_filepath(name)
        if not fp:
            print(f"  [NOT FOUND] {name}"); continue
        with open(fp, 'r', encoding='utf-8') as f:
            c = f.read()
        new = fix_hero_2_split(c, name)
        if new != c:
            with open(fp, 'w', encoding='utf-8') as f:
                f.write(new)
            print(f"  [PATCHED] {name}"); sp += 1
        else:
            print(f"  [skip] {name}")

    for name in HERO_2_NON_SPLIT:
        fp = get_filepath(name)
        if not fp:
            print(f"  [NOT FOUND] {name}"); continue
        with open(fp, 'r', encoding='utf-8') as f:
            c = f.read()
        new = fix_hero_2_non_split(c)
        if new != c:
            with open(fp, 'w', encoding='utf-8') as f:
                f.write(new)
            print(f"  [PATCHED] {name}"); ns += 1
        else:
            print(f"  [skip] {name}")

    print(f"\nhero-2 split: {sp}/{len(HERO_2_SPLIT)}")
    print(f"hero-2 non-split: {ns}/{len(HERO_2_NON_SPLIT)}")


if __name__ == "__main__":
    main()
