import sys
import os
import requests

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config_manager import get_config

def main():
    config = get_config()
    key = config.get("google_api_key")
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {"query": "restaurant in Cotonou", "key": key}
    r = requests.get(url, params=params)
    print("Status code:", r.status_code)
    print("Response JSON:", r.json())
    
if __name__ == "__main__":
    main()
