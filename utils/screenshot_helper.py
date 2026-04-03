from playwright.sync_api import sync_playwright
import os

def capture_site_mobile(url, output_path):
    """Prend une capture d'écran mobile du site."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={'width': 390, 'height': 844}, user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 14_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1")
            page = context.new_page()
            page.goto(url, timeout=30000, wait_until="networkidle")
            page.wait_for_timeout(2000)
            page.screenshot(path=output_path, full_page=False)
            browser.close()
            return True
    except Exception as e:
        print(f"Erreur screenshot: {e}")
        return False
