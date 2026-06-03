# -*- coding: utf-8 -*-
import os
import re

def search_files(directory, query_pattern):
    results = []
    regex = re.compile(query_pattern, re.IGNORECASE)
    
    for root, dirs, files in os.walk(directory):
        # Skip some folders
        if any(p in root for p in ['.git', '.venv', '__pycache__', 'node_modules', '.agent', '.claude']):
            continue
        for file in files:
            if file.endswith('.py') or file.endswith('.js') or file.endswith('.json') or file.endswith('.html'):
                path = os.path.join(root, file)
                try:
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        for line_num, line in enumerate(f, 1):
                            if regex.search(line):
                                results.append((path, line_num, line.strip()))
                except Exception as e:
                    pass
    return results

def main():
    print("Searching for 'sqlite3' or '.db' or 'connect(' in python/config files...")
    res = search_files('.', r'sqlite3|connect\b|\.db\b')
    for path, line, content in res[:100]:
        # Print only relevant lines
        if any(keyword in content for keyword in ['connect', '.db', 'sqlite3', 'db_path', 'DB_PATH']):
            print(f"{path}:{line}: {content[:100]}")
            
if __name__ == "__main__":
    main()
