"""Verify all templates have correct min-height."""
from pathlib import Path
import re

BASE = Path(__file__).parent / 'templates_sites'
print('=== VERIFICATION FINALE ===')
print()

all_ok = True
for fp in sorted(BASE.rglob('*.html')):
    try:
        html = fp.read_text(encoding='utf-8')
    except:
        html = fp.read_text(encoding='latin-1')
    
    if 'class="hero"' not in html:
        continue
    
    rel = str(fp.relative_to(BASE))
    
    mh_values = []
    for m in re.finditer(r'\.hero\s*\{[^}]*min-height[^}]*\}', html, re.DOTALL):
        val = re.search(r'min-height:\s*([^;}]+)', m.group())
        if val:
            start = m.start()
            before = html[max(0,start-400):start]
            in_mq = '@media' in before and '1024' in before
            v = val.group(1).strip()
            mh_values.append((v, 'MQ' if in_mq else 'BASE'))
    
    if not mh_values:
        print(f'  NO mh: {rel}')
        all_ok = False
        continue
    
    has_base_70 = any(v == '70svh' and ctx == 'BASE' for v, ctx in mh_values)
    has_mq_100 = any(v == '100svh' and ctx == 'MQ' for v, ctx in mh_values)
    has_bad_mq = any(v != '100svh' and ctx == 'MQ' for v, ctx in mh_values)
    has_bad_base = any(v != '70svh' and ctx == 'BASE' for v, ctx in mh_values)
    extra_rules = len(mh_values) > 2
    
    if has_base_70 and has_mq_100 and not has_bad_mq and not has_bad_base and not extra_rules:
        pass
    else:
        print(f'  {rel}: {mh_values}')
        all_ok = False

if all_ok:
    print('OK: TOUS LES TEMPLATES ONT 70svh BASE + 100svh MQ (2 regles max)')
else:
    print('WARNING: Certains templates ont encore des anomalies')
