# -*- coding: utf-8 -*-
import requests

def test_endpoint(url):
    print(f"\nTesting: {url}")
    try:
        r = requests.get(url, timeout=5)
        print(f"Status Code: {r.status_code}")
        print(f"Headers:     {r.headers.get('Content-Type')}")
        if r.status_code == 200:
            print("Content Preview (first 100 chars):")
            print(f"  {r.text[:100].strip()}...")
        else:
            print(f"Error Content: {r.text[:100]}")
    except Exception as e:
        print(f"Connection failed: {e}")

def main():
    print("=== TESTING LOCAL PWA ENDPOINTS ===")
    test_endpoint("http://localhost:5001/manifest.json")
    test_endpoint("http://localhost:5001/sw.js")
    test_endpoint("http://localhost:5001/static/icon-512.png")

if __name__ == '__main__':
    main()
