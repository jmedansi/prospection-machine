import asyncio
import os
import sys

# Ensure prospection-machine is on sys.path
sys.path.insert(0, r"d:\prospection-machine")

from reporter import main as reporter_main

mock = {
    "lead_id": 999999,
    "nom": "Test Prospect NoSite",
    "ville": "TestVille",
    "template_used": "maquette",
    "rating": 4.2,
    "reviews_count": 12,
    "category": "test",
    "telephone": "+33123456789",
    "arguments": ["Augmenter les réservations", "Meilleure visibilité locale", "Conversion mobile optimisée"]
}

async def run_test():
    url = await reporter_main.generate_and_publish_report(mock)
    print("REPORT_URL:", url)
    # check local file
    slug = url.replace("local://", "").strip('/\n')
    reports_dir = os.path.join(os.path.dirname(reporter_main.__file__), 'reports')
    local_path = os.path.join(reports_dir, slug, 'index.html')
    print("LOCAL_HTML:", local_path)
    print("EXISTS:", os.path.exists(local_path))

if __name__ == '__main__':
    asyncio.run(run_test())
