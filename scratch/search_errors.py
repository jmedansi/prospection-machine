# -*- coding: utf-8 -*-
import os

def main():
    log_path = 'errors.log'
    if not os.path.exists(log_path):
        log_path = '../errors.log'
        
    print("=== SEARCHING ERRORS.LOG FOR RESEND ERRORS ===")
    found = 0
    if os.path.exists(log_path):
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if 'resend' in line.lower() or 'email_sender' in line.lower():
                    print(line.strip())
                    found += 1
                    if found >= 50:
                        print("... truncated after 50 matches ...")
                        break
        print(f"Total matching lines found: {found}")
    else:
        print("errors.log file not found.")

if __name__ == '__main__':
    main()
