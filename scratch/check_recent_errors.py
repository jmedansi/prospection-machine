with open('dashboard/errors.log', 'r', encoding='utf-8', errors='ignore') as f:
    # Read last 5000 lines
    lines = f.readlines()
    last_lines = lines[-5000:]

print("RECENT LOG LINES WITH ERROR/EXCEPTION:")
for idx, line in enumerate(last_lines):
    if "ERROR" in line or "Exception" in line or "Traceback" in line:
        print(f"Index {idx - len(last_lines)}: {line.strip()}")
