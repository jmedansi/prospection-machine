import requests, time, json
url = 'http://127.0.0.1:5001/api/leads/enrich/status'
interval = 5
timeout = 30
start = time.time()
last = None
print('Polling', url)
while time.time() - start < timeout:
    try:
        r = requests.get(url, timeout=5)
        try:
            j = r.json()
            print(time.strftime('%H:%M:%S'), json.dumps(j, ensure_ascii=False))
            last = j
            # stop early if not running or progress 100
            if not j.get('running', True) or j.get('progress', 0) >= 100 or j.get('status') in ('idle','done','completed'):
                break
        except Exception:
            print(time.strftime('%H:%M:%S'), 'Non-JSON response:', r.text)
    except Exception as e:
        print(time.strftime('%H:%M:%S'), 'ERROR', e)
    time.sleep(interval)
print('Done. Last status:')
print(json.dumps(last, ensure_ascii=False))
