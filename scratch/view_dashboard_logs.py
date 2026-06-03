# -*- coding: utf-8 -*-
import os

def check_file(path):
    print(f"\n=== INSPECTING {path} ===")
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            print(f"Total lines: {len(lines)}")
            # print last 50 lines
            for line in lines[-50:]:
                print(line.strip())
    else:
        print(f"File {path} does not exist.")

def main():
    check_file('dashboard.log')
    check_file('server.log')
    check_file('flask.log')

if __name__ == '__main__':
    main()
