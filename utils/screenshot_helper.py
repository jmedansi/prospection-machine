import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.browser import cdp_tab_headless


def capture_site_mobile(url, output_path):
    """Prend une capture d'écran mobile du site via un Chromium local HEADLESS."""
    try:
        with cdp_tab_headless(viewport={"width": 390, "height": 844}) as page:
            page.goto(url, timeout=30000, wait_until="networkidle")
            page.wait_for_timeout(2000)
            page.screenshot(path=output_path, full_page=False)
        return True
    except Exception as e:
        print(f"Erreur screenshot: {e}")
        return False
