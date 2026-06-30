from pathlib import Path
import re

root = Path(__file__).parent / "templates_sites"
files = sorted(root.rglob('*.html'))
patterns = [
    (re.compile(r'Note\s+4\.8/5'), 'Note {{RATING}}/5'),
    (re.compile(r'Note\s+4\.8\s*/\s*5'), 'Note {{RATING}} / 5'),
    (re.compile(r'Note\s+4\.8(?![0-9A-Za-z])'), 'Note {{RATING}}'),
    (re.compile(r'4\.8/5'), '{{RATING}}/5'),
    (re.compile(r'4\.8\s*/\s*5'), '{{RATING}} / 5'),
    (re.compile(r'4\.8★'), '{{RATING}}★'),
    (re.compile(r'>(\s*)4\.8(\s*)<'), r'>\1{{RATING}}\2<'),
]

changed = []
for file_path in files:
    text = file_path.read_text(encoding='utf-8')
    new_text = text
    for pat, repl in patterns:
        new_text = pat.sub(repl, new_text)
    if new_text != text:
        file_path.write_text(new_text, encoding='utf-8')
        changed.append(str(file_path.relative_to(root)))

print(f'Patched {len(changed)} files:')
for item in changed:
    print(item)
