import ast, sys

files = [
    'database/schema.py',
    'dashboard/routes/lists.py',
    'database/repos/leads_repo.py',
    'dashboard/routes/leads.py',
    'dashboard/app.py',
    'dashboard/routes/__init__.py',
]

errors = []
for f in files:
    try:
        with open(f, encoding='utf-8') as fh:
            ast.parse(fh.read())
        print(f'  OK    {f}')
    except SyntaxError as e:
        errors.append((f, e))
        print(f'  ERROR {f}: {e}')

if errors:
    sys.exit(1)
print('\nTout OK — aucune erreur de syntaxe')
