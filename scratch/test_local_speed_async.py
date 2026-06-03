import asyncio
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT)

from core.browser import cdp_tab_headless

async def test_local_speed(url):
    print(f"Testing local load time for: {url}")
    start = time.time()
    try:
        async with cdp_tab_headless() as page:
            await page.goto(url, wait_until="load", timeout=30000)
            title = await page.title()
            print(f"Loaded title: {title}")
    except Exception as e:
        print(f"Failed to load: {e}")
        return 30000
        
    duration_ms = int((time.time() - start) * 1000)
    print(f"Load time: {duration_ms} ms")
    return duration_ms

async def main():
    await test_local_speed("https://trouver-avocats.fr")
    await test_local_speed("https://depann-assistance.com")

if __name__ == "__main__":
    asyncio.run(main())
