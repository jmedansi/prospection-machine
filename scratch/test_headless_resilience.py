import os
import sys
import logging

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT)

from core.browser import cdp_tab_headless

def test_headless():
    url = "https://www.google.com"
    print(f"Testing headless navigation to {url}...")
    try:
        with cdp_tab_headless() as page:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            title = page.title()
            print(f"[OK] Success! Title: {title}")
    except Exception as e:
        print(f"[ERR] Failed: {e}")

if __name__ == "__main__":
    test_headless()
