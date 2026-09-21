from pathlib import Path
for f in ['templates_sites/artisan/artisan-hero-1-robuste.html', 'templates_sites/auto/auto-hero-1-technique.html', 'templates_sites/auto/auto-hero-2-moderne.html']:
    html = Path(f).read_text(encoding='utf-8')
    idx = html.find('@media (min-width: 1024px)')
    mq = html[idx:idx+800]
    print(f'--- {f.split("/")[-1]} ---')
    print(mq[:500])
    print()
