import asyncio
import os
import sys

# Set ROOT
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT)

from auditeur.agents.web_analyzer import run_web_analysis

async def test_audit():
    # A fake domain that doesn't exist to simulate network error or timeout
    url = "https://this-site-will-definitely-timeout-or-error.com"
    print(f"Testing audit for {url}...")
    
    results = await run_web_analysis(url)
    
    print("\n--- RESULTS ---")
    print(f"Mobile Score: {results.get('mobile_score')}")
    print(f"Desktop Score: {results.get('desktop_score')}")
    print(f"Mobile LCP: {results.get('mobile_lcp_ms')}")
    print(f"PageSpeed Error: {results.get('pagespeed_error')}")
    print(f"HTTP Error: {results.get('http_error')}")

if __name__ == "__main__":
    asyncio.run(test_audit())
