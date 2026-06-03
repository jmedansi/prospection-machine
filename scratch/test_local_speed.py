import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT)

from core.browser import cdp_tab_headless

def test_local_speed(url):
    print(f"Testing local load time for: {url}")
    start = time.time()
    try:
        with cdp_tab_headless() as page:
            page.goto(url, wait_until="load", timeout=30000)
            # get title to prove we loaded it
            title = page.title()
            print(f"Loaded title: {title}")
    except Exception as e:
        print(f"Failed to load: {e}")
        return 30000
        
    duration_ms = int((time.time() - start) * 1000)
    print(f"Load time: {duration_ms} ms")
    return duration_ms

if __name__ == "__main__":
    test_local_speed("https://trouver-avocats.fr")
    test_local_speed("https://depann-assistance.com")
