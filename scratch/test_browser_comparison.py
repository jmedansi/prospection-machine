import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT)

from core.browser import cdp_tab, cdp_tab_headless

def compare_browsers(url):
    print(f"Comparing access to {url}...")
    
    # Test Headless
    print("\n--- [1] Headless Browser ---")
    try:
        with cdp_tab_headless() as page:
            start = time.time()
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            print(f"[OK] Headless success in {time.time()-start:.2f}s. Title: {page.title()}")
    except Exception as e:
        print(f"[FAIL] Headless failed: {e}")

    # Test Persistent (Main)
    print("\n--- [2] Persistent Browser (Main) ---")
    try:
        with cdp_tab() as page:
            start = time.time()
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            print(f"[OK] Persistent success in {time.time()-start:.2f}s. Title: {page.title()}")
    except Exception as e:
        print(f"[FAIL] Persistent failed: {e}")

if __name__ == "__main__":
    url = "https://exatice.com"
    compare_browsers(url)
