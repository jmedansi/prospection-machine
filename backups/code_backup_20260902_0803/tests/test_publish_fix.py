# -*- coding: utf-8 -*-
import os
import sys
import time
import base64

# Add root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from synthetiseur.github_publisher import push_audit_to_github, flush_pending_reports

def test_publish():
    print("Testing GitHub publish with screenshots...")
    
    # Create a dummy image for testing
    img_path = os.path.join(os.path.dirname(__file__), "test_img.png")
    with open(img_path, "wb") as f:
        # 1x1 black dot PNG
        f.write(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="))
    
    slug = "test-audit-fix"
    html_content = f"<html><body><h1>Test Audit Fix</h1><img src='test_img.png'></body></html>"
    screenshots = {
        "screenshot_desktop": img_path
    }
    
    print(f"Queueing report for {slug}...")
    url, _ = push_audit_to_github(slug, html_content, screenshots)
    
    print("Flushing batch...")
    flush_pending_reports()
    
    print(f"Check URL: {url}")
    print(f"Images should be at: {url}test_img.png")
    
    # Cleanup
    if os.path.exists(img_path):
        os.remove(img_path)

if __name__ == "__main__":
    test_publish()
