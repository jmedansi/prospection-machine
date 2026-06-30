import os
from datetime import datetime

log_files = []
for root, dirs, files in os.walk('.'):
    if '.venv' in root or '.git' in root:
        continue
    for file in files:
        if file.endswith('.log'):
            path = os.path.join(root, file)
            try:
                mtime = os.path.getmtime(path)
                log_files.append((path, mtime))
            except Exception:
                pass

log_files.sort(key=lambda x: x[1], reverse=True)
print("RECENTLY MODIFIED LOG FILES:")
for path, mtime in log_files[:20]:
    print(f"  {path} : {datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')}")
