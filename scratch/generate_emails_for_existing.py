# -*- coding: utf-8 -*-
import sys
import os
import logging

# Add project root to sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sniper.email_generator import generate_sniper_emails_batch

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def main():
    print("=== STARTING EMAIL GENERATION BATCH ===")
    res = generate_sniper_emails_batch(limit=100)
    print("\n=== BATCH RUN RESULT ===")
    print(f"Successfully generated: {res['success']}")
    print(f"Skipped/Ignored: {res['skipped']}")
    print(f"Errors/Failed: {res['failed']}")

if __name__ == '__main__':
    main()
