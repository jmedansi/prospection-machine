from pathlib import Path
fp = Path('synthetiseur/rapports/test_artisan-1.html')
html = fp.read_text(encoding='utf-8')

# Show ALL .hero related rules
import re
for m in re.finditer(r'\.hero[^{]*\{[^}]*\}', html):
    print(m.group())
    print()

# Find hero-content class
idx = html.find('hero-content')
print("\nhero-content HTML:")
print(html[idx-50:idx+600])
