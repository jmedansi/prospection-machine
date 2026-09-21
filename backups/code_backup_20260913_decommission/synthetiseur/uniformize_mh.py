"""Uniformise tous les templates : 70svh base + 100svh dans dernière MQ 1024."""
from pathlib import Path
import re

BASE = Path(__file__).parent / 'templates_sites'
FILES = sorted(BASE.rglob('*.html'))

# Files we already fixed (skip them)
ALREADY_DONE = {
    'artisan/artisan-hero-1-robuste.html',
    'auto/auto-hero-1-technique.html', 
    'auto/auto-hero-2-moderne.html',
}

def fix_file(fp):
    rel = str(fp.relative_to(BASE.parent.parent))  # relative to synthetiseur
    try:
        html = fp.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        html = fp.read_text(encoding='latin-1')
    
    original = html
    name = fp.name
    
    # ── 1. Find base .hero CSS rule ──
    # Look for the first .hero rule that contains position/flex (the structural one)
    base_hero_match = None
    for m in re.finditer(r'\.hero\s*\{[^}]*\}', html, re.DOTALL):
        rule = m.group()
        # Skip if inside @media
        start = m.start()
        before = html[max(0,start-300):start]
        if '@media' in before:
            continue
        # This is a base rule (not in MQ)
        if not base_hero_match or ('position' in rule and 'flex' in rule):
            base_hero_match = m
        elif not base_hero_match:
            base_hero_match = m
    
    if base_hero_match:
        rule = base_hero_match.group()
        new_rule = rule
        
        # If it has min-height, change the value
        if 'min-height' in new_rule:
            if '75svh' in new_rule or '80svh' in new_rule or '100svh' in new_rule:
                new_rule = re.sub(r'min-height:\s*\d+svh(\s*!important)?', 'min-height: 70svh', new_rule)
        else:
            # Add min-height before the closing brace
            new_rule = new_rule.rstrip()
            if new_rule.endswith('}'):
                # Check if there are already properties
                inner = new_rule[:-1].strip()
                if inner.endswith(';'):
                    new_rule = inner + ' min-height: 70svh; }'
                elif inner.endswith('{'):
                    new_rule = inner + ' min-height: 70svh; }'
                elif '{' in inner:
                    # Has properties but last doesn't end with ;
                    new_rule = inner.rstrip() + '; min-height: 70svh; }'
                else:
                    new_rule = inner + ' min-height: 70svh; }'
        
        html = html[:base_hero_match.start()] + new_rule + html[base_hero_match.end():]
    
    # ── 2. Remove any .hero { min-height: ... } that's inside MQ ──
    # (We'll re-add 100svh explicitly in the LAST MQ)
    def remove_mq_hero_mh(match):
        full = match.group()
        # Only remove min-height rules from .hero inside MQ
        # But we need to be careful not to remove other min-height rules
        start = match.start()
        before = html[max(0,start-400):start]
        if '@media' in before:
            # Remove just the min-height from this rule
            full = re.sub(r'min-height:\s*\d+svh(\s*!important)?\s*;?\s*', '', full)
            # Clean up empty braces or trailing semi
            full = re.sub(r'\{[\s;]*\}', '{}', full)
        return full
    
    html = re.sub(r'\.hero\s*\{[^}]*min-height[^}]*\}', remove_mq_hero_mh, html, flags=re.DOTALL)
    
    # ── 3. Find last @media (min-width: 1024px) and add .hero { min-height: 100svh; } ──
    last_idx = -1
    for m in re.finditer(r'@media\s*\(min-width:\s*1024px\)\s*\{[^}]*\}', html, re.DOTALL):
        last_idx = m.start()
        last_mq = m.group()
    
    if last_idx >= 0:
        # Find the closing brace of this MQ and insert before it
        mq_end = html.find('}', last_idx)
        # Actually need to find matching closing brace (might be nested)
        # Simple approach: find last } after the MQ starts
        # Since we already matched the MQ group, we know its end
        last_mq_end = m.lastgroup_end if hasattr(m, 'lastgroup_end') else None
        # Let's just use the regex match end
        for m in re.finditer(r'@media\s*\(min-width:\s*1024px\)\s*\{[^}]*\}', html, re.DOTALL):
            last_mq_end = m.end()
        
        if last_mq_end:
            insert_pos = last_mq_end - 1  # before the closing }
            # Check if .hero min-height already exists inside
            mq_block = html[last_idx:last_mq_end]
            if '.hero' in mq_block and 'min-height' in mq_block:
                # Already has hero min-height, skip (but we already removed it)
                pass
            html = html[:insert_pos] + '\n  .hero { min-height: 100svh; }\n' + html[insert_pos:]
    
    # ── 4. Write back if changed ──
    if html != original:
        encoding = 'utf-8'
        try:
            original.encode('utf-8')
        except UnicodeEncodeError:
            encoding = 'latin-1'
        fp.write_bytes(html.encode(encoding))
        print(f'  OK  {name}')
        return True
    else:
        # print(f'  —   {name} (unchanged)')
        return False

print('Fixing min-height: 70svh base + 100svh MQ 1024...')
count = 0
for fp in FILES:
    rel = str(fp.relative_to(BASE))
    if rel in ALREADY_DONE:
        continue
    # Skip non-hero files
    html_test = fp.read_bytes()
    if b'class="hero"' not in html_test and b"class='hero'" not in html_test:
        continue
    if fix_file(fp):
        count += 1

print(f'\nDone: {count} files modified')
