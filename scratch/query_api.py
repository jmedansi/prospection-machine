# -*- coding: utf-8 -*-
import requests

def main():
    # Query stats
    print("Querying /api/stats...")
    try:
        r = requests.get('http://127.0.0.1:5001/api/stats?v=5')
        print(r.json())
    except Exception as e:
        print(f"Error stats: {e}")
        
    print("\nQuerying /api/collectes...")
    try:
        r = requests.get('http://127.0.0.1:5001/api/collectes')
        print(r.json())
    except Exception as e:
        print(f"Error collectes: {e}")
        
    print("\nQuerying /api/leads/all...")
    try:
        r = requests.get('http://127.0.0.1:5001/api/leads/all?limit=5')
        data = r.json()
        print(f"Total leads in API: {data.get('total')}")
        print("First few leads:")
        for lead in data.get('leads', []):
            print(f"  ID: {lead['id']} | Nom: {lead['nom']} | Source: {lead['source']} | Secteur: {lead['secteur']} | Statut: {lead['statut']} | campaign_id: {lead.get('campaign_id')}")
    except Exception as e:
        print(f"Error leads: {e}")

if __name__ == "__main__":
    main()
