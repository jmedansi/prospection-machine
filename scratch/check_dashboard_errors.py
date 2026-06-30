import sys
with open('dashboard/errors.log', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

print("LAST 50 LINES of dashboard/errors.log:")
for line in lines[-50:]:
    print(line.strip())
