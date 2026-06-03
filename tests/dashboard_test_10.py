import requests
import time
import os

URL = 'http://127.0.0.1:5001/api/audit/launch'

def main():
    results = []
    for i in range(10):
        try:
            r = requests.post(URL, json={'limit': 1}, timeout=10)
            print(f"[{i+1}/10] {r.status_code} {r.text}")
            results.append((r.status_code, r.text))
        except Exception as e:
            print(f"[{i+1}/10] ERROR {e}")
            results.append(('ERROR', str(e)))
        time.sleep(0.2)

    # show queue counts
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    qbase = os.path.join(base, 'audit_queue')
    def count(dir_name):
        p = os.path.join(qbase, dir_name)
        try:
            return len([f for f in os.listdir(p) if f.endswith('.json')])
        except Exception:
            return 'N/A'

    print('PENDING:', count('pending'))
    print('PROCESSING:', count('processing'))
    print('HISTORY:', count('history'))

if __name__ == '__main__':
    main()
