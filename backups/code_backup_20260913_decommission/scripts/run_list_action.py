import sys, requests, json

if len(sys.argv) < 3:
    print('Usage: run_list_action.py <list_id> <action> [base_url]')
    sys.exit(2)

list_id = sys.argv[1]
action = sys.argv[2]
base = sys.argv[3] if len(sys.argv) > 3 else 'http://127.0.0.1:5001'

url = f"{base}/api/lists/{list_id}/actions"
print(f"POST {url} -> action={action}")
try:
    r = requests.post(url, json={'action': action}, timeout=60)
    try:
        j = r.json()
        print('STATUS', r.status_code)
        print(json.dumps(j, ensure_ascii=False, indent=2))
    except Exception:
        print('STATUS', r.status_code)
        print(r.text)
except Exception as e:
    print('ERROR', e)
    sys.exit(1)
