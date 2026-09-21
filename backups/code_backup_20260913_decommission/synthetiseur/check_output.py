from pathlib import Path

path = Path(__file__).parent / 'rapports' / 'rapport_1_Sacrée_Fleur_Montmartre.html'
text = path.read_text(encoding='utf-8')
print('path:', path)
for keyword in ['LOGO_URL', 'profil-a-preview-section', 'profil-a-header', 'NB_AVIS', 'RATING', '4.8/5', '4.8★', '4.8']:
    print(keyword, keyword in text)
print('\n--- SNIPPET 1 ---')
for line in text.splitlines():
    if any(k in line for k in ['profil-a-preview-section', 'profil-a-header', 'Note', 'avis', 'LOGO_URL', 'RATING']):
        print(line)
print('\n--- SNIPPET 2 ---')
for pattern in ['4.8/5', '4.8★', 'Note', 'avis', 'nombre']:
    if pattern in text:
        idx = text.index(pattern)
        start = max(0, idx-80)
        end = min(len(text), idx+80)
        print('PATTERN:', pattern, '=>', text[start:end].replace('\n',' '))
