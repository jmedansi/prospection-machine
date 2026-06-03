# -*- coding: utf-8 -*-
import os

def main():
    log_path = 'errors.log'
    if not os.path.exists(log_path):
        log_path = '../errors.log'
        
    print("=== READING RECENT LOGS ===")
    if os.path.exists(log_path):
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            recent_lines = lines[-50:]
            print(f"Total lines in log: {len(lines)}")
            print("--- LAST 50 LINES ---")
            for line in recent_lines:
                print(line.strip())
    else:
        print("errors.log file not found.")

if __name__ == '__main__':
    main()
