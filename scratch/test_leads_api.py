# -*- coding: utf-8 -*-
import requests
import time

def main():
    print("=== TIMING TEST FOR /api/leads/all ===")
    url = "http://127.0.0.1:5001/api/leads/all?page=1&limit=50"
    
    start_time = time.time()
    try:
        r = requests.get(url, timeout=30)
        elapsed = time.time() - start_time
        print(f"Status Code: {r.status_code}")
        print(f"Response Time: {elapsed:.3f} seconds")
        if r.status_code == 200:
            data = r.json()
            leads_count = len(data.get("leads", []))
            total = data.get("total", 0)
            print(f"Total leads in DB: {total}")
            print(f"Leads returned in page: {leads_count}")
        else:
            print(f"Error: {r.text[:200]}")
    except Exception as e:
        print(f"Request failed or timed out: {e}")

if __name__ == '__main__':
    main()
