# -*- coding: utf-8 -*-
import os

def search_word(word):
    print(f"\nSearching for references to '{word}':")
    for root, dirs, files in os.walk('.'):
        if any(p in root for p in ['.git', '.venv', '__pycache__', 'node_modules', '.agent', '.claude']):
            continue
        for file in files:
            if file.endswith('.py') or file.endswith('.js') or file.endswith('.sql'):
                path = os.path.join(root, file)
                try:
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        for line_num, line in enumerate(f, 1):
                            if word in line:
                                print(f"  {path}:{line_num}: {line.strip()[:120]}")
                except Exception:
                    pass

def main():
    search_word("audit_partial")
    search_word("notified_at")
    search_word("score_lead")

if __name__ == "__main__":
    main()
