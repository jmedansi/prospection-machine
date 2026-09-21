"""Analyze all templates for hero min-height structure."""
from pathlib import Path
import re

BASE = Path(__file__).parent / 'templates_sites'

for fp in sorted(BASE.rglob('*.html')):
    try:
        html = fp.read_text(encoding='utf-8')
    except:
        html = fp.read_text(encoding='latin-1')
    
    rel = str(fp.relative_to(BASE))
    
    has_hero_html = 'class="hero"' in html or "class='hero'" in html
    
    # All .hero CSS rules
    hero_rules = []
    for m in re.finditer(r'\.hero\s*\{[^}]*min-height[^}]*\}', html, re.DOTALL):
        rule = m.group().strip()
        # Determine if inside MQ
        start = m.start()
        before = html[max(0,start-400):start]
        in_1024 = '@media' in before and '1024' in before
        hero_rules.append((rule[:80], in_1024))
    
    # All 1024 MQs
    mq_1024 = []
    for m in re.finditer(r'@media\s*\(min-width:\s*1024px\)\s*\{[^}]*\}', html, re.DOTALL):
        block = m.group()
        has_hero = '.hero' in block
        mq_1024.append((block[:60], has_hero))
    
    if hero_rules or not has_hero_html:
        print(f'{rel}: hero HTML={has_hero_html}')
        for r, in_mq in hero_rules:
            where = 'MQ1024' if in_mq else 'BASE'
            print(f'  {where}: {r}')
        if not hero_rules and has_hero_html:
            print(f'  WARNING: no min-height on .hero')
        if mq_1024:
            for b, hh in mq_1024:
                print(f'  1024MQ: has_hero={hh}: {b}')
    else:
        print(f'{rel}: no hero rules')
