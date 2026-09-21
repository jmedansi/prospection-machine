import re
from pathlib import Path

for f in ['test_artisan-artisan-1-robuste-render.html',
          'test_auto-auto-1-technique-render.html',
          'test_auto-auto-2-moderne-render.html']:
    html = (Path('rapports') / f).read_text(encoding='utf-8', errors='replace')
    print(f'=== {f} ===')
    # CSS properties
    checks = [
        ('text-wrap balance', 'text-wrap: balance'),
        ('overflow-wrap', 'overflow-wrap: break-word'),
        ('max-width 640px', 'max-width: 640px'),
        ('eyebrow mb 1.25rem', 'margin-bottom: 1.25rem'),
        ('title mb 1rem', 'margin-bottom: 1rem'),
        ('sub-line margin 1rem', 'margin: 1rem 0'),
        ('desc mb 1.5rem', 'margin-bottom: 1.5rem'),
        ('ctas gap 1rem', 'gap: 1rem'),
        ('mobile eyebrow 1.5rem', 'margin-bottom: 1.5rem !important'),
        ('mobile title 1.25rem', 'margin-bottom: 1.25rem !important'),
        ('mobile ctas 0.875rem', 'gap: 0.875rem !important'),
        ('late MQ gap 0.875rem', 'gap:0.875rem!important'),
        ('1024px+ eyebrow 1.5rem', '.hero-eyebrow { margin-bottom: 1.5rem; }'),
        ('1024px+ title 1.25rem', '.hero-title { margin-bottom: 1.25rem; }'),
        ('1024px+ sub-line 1.25rem', '.hero-sub-line { margin: 1.25rem 0; }'),
        ('1024px+ desc 1.75rem', '.hero-desc { margin-bottom: 1.75rem; }'),
        ('75svh mobile', '75svh'),
        ('no br in title', 'NOM_ENTREPRISE><em>'),
    ]
    all_ok = True
    for label, pattern in checks:
        ok = pattern in html
        if not ok:
            all_ok = False
            print(f'  FAIL: {label}')
    if all_ok:
        print(f'  ALL CHECKS PASSED')
    print()
