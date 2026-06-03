import os
import re

directories = [
    'dashboard/templates/views/sections/',
    'dashboard/templates/components/'
]

onclick_pattern = re.compile(r'onclick=["\']([^"\']+)["\']')
func_pattern = re.compile(r'([a-zA-Z0-9_]+)\s*\(')

all_calls = set()

for d in directories:
    for root, _, files in os.walk(d):
        for f in files:
            if f.endswith('.html'):
                path = os.path.join(root, f)
                with open(path, 'r', encoding='utf-8') as f_in:
                    content = f_in.read()
                    matches = onclick_pattern.findall(content)
                    for m in matches:
                        # Extract function names
                        funcs = func_pattern.findall(m)
                        for func in funcs:
                            all_calls.add(func)

print("UNIQUE FUNCTIONS CALLED IN ONCLICK:")
for func in sorted(list(all_calls)):
    print(func)
