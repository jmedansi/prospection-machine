import requests
import sys
import os
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT)
from config_manager import get_active_client

def test_raw_pagespeed(url):
    print(f"\n--- Testing PageSpeed API for {url} ---")
    
    api_key = None
    try:
        client = get_active_client()
        api_key = client.get("google_api_key")
        print(f"Using API Key: {api_key[:10]}... if exists")
    except:
        print("No active client/API key found.")

    psi_url = f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url={url}&strategy=mobile"
    if api_key:
        psi_url += f"&key={api_key}"

    try:
        print("Sending request to Google PageSpeed API...")
        resp = requests.get(psi_url, timeout=30)
        print(f"HTTP Status Code: {resp.status_code}")
        
        if resp.status_code != 200:
            try:
                error_data = resp.json()
                print(f"API Error Response: {json.dumps(error_data, indent=2)}")
            except:
                print(f"Raw Text Response: {resp.text[:500]}")
        else:
            data = resp.json()
            lh = data.get('lighthouseResult', {})
            categories = lh.get('categories', {})
            perf = categories.get('performance', {}).get('score')
            print(f"Success! Performance Score: {perf * 100 if perf else 'None'}")
            
    except Exception as e:
        print(f"Request Exception: {e}")

if __name__ == "__main__":
    test_raw_pagespeed("https://depann-assistance.com")
    test_raw_pagespeed("https://trouver-avocats.fr")
    test_raw_pagespeed("https://google.com") # Baseline test
