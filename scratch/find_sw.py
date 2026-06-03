# -*- coding: utf-8 -*-
import os

def main():
    print("=== SEARCHING FOR SERVICE WORKERS ===")
    found = []
    for root, dirs, files in os.walk('.'):
        for f in files:
            if f == 'sw.js' or f == 'service-worker.js':
                full_path = os.path.join(root, f)
                found.append(full_path)
                print(f"Found: {full_path}")
                
    if not found:
        print("No service worker files found in the project.")

if __name__ == '__main__':
    main()
